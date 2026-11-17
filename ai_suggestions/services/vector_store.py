from pathlib import Path
import re
import xml.etree.ElementTree as ElementTree
import zipfile

import chromadb
from django.conf import settings
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer


class StudyPodVectorStore:
    """Local ChromaDB store for StudyPod resource text."""

    MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
    COLLECTION_NAME = "study_resources"
    CHUNK_SIZE = 500
    CHUNK_OVERLAP = 75

    def __init__(self):
        db_path = Path(settings.BASE_DIR) / "chroma_db"
        self.client = chromadb.PersistentClient(path=str(db_path))
        self.collection = self.client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self._model = None

    @property
    def model(self):
        # Load on first use. The model must be downloaded or cached locally
        # before the machine can use it without internet access.
        if self._model is None:
            self._model = SentenceTransformer(self.MODEL_NAME)
        return self._model

    def ingest_resource(self, resource_id, file_path, metadata):
        """Extract, chunk, embed, and prepare a PDF, TXT, or XLSX resource for AI search."""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Resource file not found: {path}")

        text = self._extract_text(path)
        chunks = self._split_text(text)
        resource_key = str(resource_id)

        if not chunks:
            self.collection.delete(where={"resource_id": resource_key})
            return 0

        safe_metadata = self._clean_metadata(metadata)
        safe_metadata["resource_id"] = resource_key
        if "class_id" not in safe_metadata:
            raise ValueError("Resource metadata must include class_id.")

        ids = [f"resource-{resource_key}-chunk-{i}" for i in range(len(chunks))]
        metadatas = [
            {**safe_metadata, "chunk_index": i}
            for i in range(len(chunks))
        ]
        embeddings = self.model.encode(
            chunks,
            convert_to_numpy=True,
        ).tolist()

        # Upsert new content first, then remove any leftover chunks from an
        # earlier, longer version of the same resource.
        self.collection.upsert(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        existing = self.collection.get(
            where={"resource_id": resource_key},
            include=[],
        )
        stale_ids = [item_id for item_id in existing["ids"] if item_id not in ids]
        if stale_ids:
            self.collection.delete(ids=stale_ids)

        return len(chunks)

    def retrieve_context(self, query, class_id, n_results=3):
        """Return the closest resource chunks for one class."""
        query = (query or "").strip()
        if not query:
            raise ValueError("Query must not be empty.")
        if class_id is None:
            raise ValueError("class_id is required.")

        available = self.collection.count()
        if available == 0:
            return []

        result = self.collection.query(
            query_embeddings=[
                self.model.encode(
                    query,
                    convert_to_numpy=True,
                ).tolist()
            ],
            n_results=max(1, min(int(n_results), available)),
            where={"class_id": str(class_id)},
            include=["documents", "metadatas", "distances"],
        )

        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        ids = result.get("ids", [[]])[0]

        return [
            {
                "id": ids[index],
                "text": documents[index],
                "metadata": metadatas[index],
                "distance": distances[index],
            }
            for index in range(len(documents))
        ]

    def is_resource_indexed(self, resource_id):
        records = self.collection.get(
            where={"resource_id": str(resource_id)},
            include=[],
        )
        return bool(records.get("ids"))

    def retrieve_resource_chunks(self, resource_id, limit=8):
        records = self.collection.get(
            where={"resource_id": str(resource_id)},
            include=["documents", "metadatas"],
        )

        documents = records.get("documents") or []
        metadatas = records.get("metadatas") or []
        chunks = [
            {
                "id": records["ids"][index],
                "text": documents[index],
                "metadata": metadatas[index],
            }
            for index in range(min(len(records.get("ids", [])), len(documents), len(metadatas)))
        ]
        chunks.sort(
            key=lambda chunk: chunk["metadata"].get("chunk_index", 0)
        )
        return chunks[:max(1, int(limit))]

    def delete_resource(self, resource_id):
        records = self.collection.get(
            where={"resource_id": str(resource_id)},
            include=[],
        )
        count = len(records.get("ids", []))
        if count:
            self.collection.delete(where={"resource_id": str(resource_id)})
        return count

    @staticmethod
    def _extract_text(path):
        suffix = path.suffix.lower()

        if suffix == ".pdf":
            reader = PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)

        if suffix == ".txt":
            return path.read_text(encoding="utf-8", errors="replace")

        if suffix == ".xlsx":
            return StudyPodVectorStore._extract_xlsx_text(path)

        raise ValueError("This file type is not supported for AI search. Use a PDF, TXT, or XLSX file.")

    @staticmethod
    def _extract_xlsx_text(path):
        """Read visible cell values from an Excel workbook using the standard library."""
        namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        text_namespace = namespace + "t"
        shared_strings = []

        with zipfile.ZipFile(path) as workbook:
            if "xl/sharedStrings.xml" in workbook.namelist():
                shared_root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
                shared_strings = [
                    "".join(node.text or "" for node in item.iter(text_namespace))
                    for item in shared_root.findall(namespace + "si")
                ]

            sheet_paths = sorted(
                name for name in workbook.namelist()
                if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
            )
            extracted_sheets = []
            for sheet_number, sheet_path in enumerate(sheet_paths, start=1):
                sheet_root = ElementTree.fromstring(workbook.read(sheet_path))
                rows = []
                for row in sheet_root.iter(namespace + "row"):
                    values = []
                    for cell in row.findall(namespace + "c"):
                        value_node = cell.find(namespace + "v")
                        cell_type = cell.attrib.get("t")
                        if cell_type == "inlineStr":
                            value = "".join(
                                node.text or ""
                                for node in cell.iter(text_namespace)
                            )
                        elif value_node is None or value_node.text is None:
                            value = ""
                        elif cell_type == "s":
                            try:
                                value = shared_strings[int(value_node.text)]
                            except (ValueError, IndexError):
                                value = ""
                        else:
                            value = value_node.text
                        if value:
                            values.append(str(value))
                    if values:
                        rows.append(" | ".join(values))
                if rows:
                    extracted_sheets.append(
                        f"Sheet {sheet_number}:\n" + "\n".join(rows)
                    )

        return "\n\n".join(extracted_sheets)

    def _split_text(self, text):
        text = " ".join((text or "").split())
        if not text:
            return []

        step = self.CHUNK_SIZE - self.CHUNK_OVERLAP
        return [
            text[start:start + self.CHUNK_SIZE]
            for start in range(0, len(text), step)
        ]

    @staticmethod
    def _clean_metadata(metadata):
        """Keep only scalar values supported by ChromaDB."""
        cleaned = {}
        for key, value in (metadata or {}).items():
            if value is None:
                continue
            if isinstance(value, (str, int, float, bool)):
                cleaned[str(key)] = str(value) if key == "class_id" else value
        return cleaned
