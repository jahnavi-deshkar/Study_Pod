from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import StudentProfile, TeacherProfile
from academics.models import Class, DoubtReply, DoubtThread, Notice, Resource, Subject


RESOURCES = (
    (
        "DSP-ALG", "Mathematical_Logic_Truth_Tables_Notes.txt",
        "Mathematical Logic & Truth Tables",
        """DSP Academy | Mathematical Logic Quick Notes

Propositions and connectives
 p  q | p AND q | p OR q | p -> q | p <-> q
 T  T |    T    |   T    |    T   |     T
 T  F |    F    |   T    |    F   |     F
 F  T |    F    |   T    |    T   |     F
 F  F |    F    |   F    |    T   |     T

Implication is false only when its premise is true and conclusion false.
Negation of an implication: not(p -> q) = p AND not(q).
De Morgan: not(p AND q) = not(p) OR not(q); not(p OR q) = not(p) AND not(q).
A tautology is true in every row; a contradiction is false in every row.
For a compound proposition, build one column per sub-expression and evaluate
from the innermost parentheses outward.
""",
    ),
    (
        "DSP-TRIG", "Trigonometry_Compound_Angles_Sheet.txt",
        "Trigonometry Compound Angles & Identities",
        """DSP Academy | Compound Angle Formula Sheet

sin(A+B) = sin A cos B + cos A sin B
sin(A-B) = sin A cos B - cos A sin B
cos(A+B) = cos A cos B - sin A sin B
cos(A-B) = cos A cos B + sin A sin B
tan(A+B) = (tan A + tan B) / (1 - tan A tan B)
tan(A-B) = (tan A - tan B) / (1 + tan A tan B)

Double angles: sin 2A = 2 sin A cos A; cos 2A = cos^2 A - sin^2 A.
Product-to-sum: 2 sin A cos B = sin(A+B) + sin(A-B).
Before using an identity, check the quadrant and the signs of each ratio.
""",
    ),
    (
        "DSP-VECT", "Vectors_3D_Plane_Equations_Summary.txt",
        "Vectors, 3D Lines & Plane Equations",
        """DSP Academy | Vectors and 3D Geometry

For vectors a=(a1,a2,a3), b=(b1,b2,b3):
a dot b = a1*b1 + a2*b2 + a3*b3
|a cross b| = |a||b| sin(theta); a dot b = |a||b| cos(theta).

Line through r0 with direction d: r = r0 + t d.
Plane through (x0,y0,z0) with normal (A,B,C):
A(x-x0) + B(y-y0) + C(z-z0) = 0.
Angle theta between a line (direction d) and a plane (normal n):
sin(theta) = |d dot n| / (|d||n|), with 0 <= theta <= 90 degrees.
Distance from (x1,y1,z1) to Ax+By+Cz+D=0 is
|Ax1+By1+Cz1+D| / sqrt(A^2+B^2+C^2).
""",
    ),
    (
        "DSP-CALC", "Calculus_Integration_Standard_Formulae.txt",
        "Calculus: Differentiation & Integration Formulae",
        """DSP Academy | Calculus Formulae and Methods

Differentiation
d(x^n)/dx = n*x^(n-1); d(sin x)/dx = cos x; d(cos x)/dx = -sin x.
d(e^x)/dx = e^x; d(ln x)/dx = 1/x.
Product rule: (uv)' = u'v + uv'. Quotient rule: (u/v)'=(u'v-uv')/v^2.
Chain rule: d[f(g(x))]/dx = f'(g(x))*g'(x).

Standard integrals
integral x^n dx = x^(n+1)/(n+1) + C (n != -1).
integral dx/x = ln|x| + C; integral e^x dx = e^x + C.
integral sin x dx = -cos x + C; integral cos x dx = sin x + C.
integral dx/(a^2+x^2) = (1/a) atan(x/a) + C (a>0).
Integration by parts: integral u dv = uv - integral v du.
For substitution, set u=g(x), replace dx and all limits together.
Fundamental theorem: integral_a^b f(x)dx = F(b)-F(a), where F'=f.
""",
    ),
    (
        "DSP-PROB", "Probability_Binomial_Distribution_Notes.txt",
        "Probability & Binomial Distribution Notes",
        """DSP Academy | Probability and Binomial Distribution

For independent trials with success probability p and q=1-p, if X is the
number of successes in n trials, then X ~ Binomial(n,p).
P(X=r) = C(n,r) p^r q^(n-r), r=0,1,...,n.
Mean E[X] = np; variance Var(X) = npq; standard deviation = sqrt(npq).

Useful counting: C(n,r) = n! / (r!(n-r)!).
Check that probabilities are between 0 and 1 and their complete distribution
sums to 1. For an event described as “at least one”, use the complement:
P(X>=1) = 1 - P(X=0) = 1 - q^n.
""",
    ),
    (
        "DSP-MOCK", "MHTCET_2026_Shortcut_Tricks_Compendium.txt",
        "MHT-CET 2026 Mathematics Mock-Test Strategy",
        """DSP Academy | Mathematics Mock-Test Strategy

Use the first pass to secure short, familiar questions. Mark lengthy algebra
and return on a second pass. Keep rough work aligned with question numbers so
answers can be checked quickly. Reserve the final minutes for unanswered
items, sign checks, units, and transferring responses to the required format.

Fast checks
* Substitute a proposed root into the original equation.
* Use parity and domain restrictions before expanding expressions.
* In determinants, look for a common factor or equal rows before expansion.
* In probability, count the sample space once and avoid double-counting.
* In calculus, differentiate an antiderivative to check an integral.
Follow the official instructions for the specific mock; do not assume a
shortcut replaces a required derivation in board-style answers.
""",
    ),
)

NOTICE_TOPICS = (
    (
        "MHT-CET Grand Mock 1 & 2: Exam Guidelines and Reporting",
        "Please arrive 30 minutes before the reporting time shown in the test notice. Bring your student ID and required stationery. Keep phones and smart devices away during the paper. Read the instructions before starting, manage time by section, and use the final minutes to review marked questions and answer transfers. The same conduct rules apply to both grand mocks.",
    ),
    (
        "12th HSC Mathematics Part 1 & Part 2: Prelim Discussion Schedule",
        "The Part 1 and Part 2 prelim discussions will review the paper pattern, common working errors, and the method expected for full-credit solutions. Bring your question paper and attempted rough work. Morning Batch and Evening Batch should follow the session slot shown on the academy timetable; bring unresolved questions for the final discussion period.",
    ),
    (
        "Special Doubt-Clearing Session: Definite Integration & Differential Equations",
        "A focused doubt-clearing session will cover properties of definite integrals, change of limits, integration techniques, order and degree of differential equations, and verification of solutions. Try the assigned examples first and bring the exact step where your working gets stuck. Batch-specific timing will be posted on the timetable.",
    ),
    (
        "Formula Handbook Distribution & Weekly Test Syllabus Update",
        "The mathematics formula handbook is available in Study Resources. This week's test syllabus includes the topics listed in the latest assessment notice. Use the handbook for revision, but practise deriving key results and showing intermediate steps. Check the published test list before the weekly test so you prepare from the correct topic range.",
    ),
)

THREADS = (
    (
        "m1", "DSP-CALC", "Definite integration: when can I use King's property?",
        "I know that integral from 0 to a of f(x) dx can be rewritten using f(a-x), but I am unsure how that helps when the integrand contains both x and a-x. How should I combine the two forms without changing the limits incorrectly?",
        DoubtThread.Category.SYLLABUS_TOPIC, DoubtThread.Status.RESOLVED,
        "For I = integral_0^a f(x) dx, substitute u=a-x. The limits switch from a to 0 and du=-dx, so I = integral_0^a f(a-u) du. Rename u as x: I = integral_0^a f(a-x) dx. You now have two equal expressions. Add them before simplifying: 2I = integral_0^a [f(x)+f(a-x)] dx. This is especially useful when the bracket becomes constant or symmetric. The switched limits and the minus sign cancel; that is the step to keep visible in your working.",
    ),
    (
        "m4", "DSP-VECT", "Finding the angle between a 3D line and a plane",
        "For a line with direction ratios (2,-1,2) and a plane with normal (1,2,2), should I use the dot product directly for the line-plane angle? I get the complementary angle depending on which vectors I compare.",
        DoubtThread.Category.SYLLABUS_TOPIC, DoubtThread.Status.RESOLVED,
        "The dot product gives the angle between the line direction d and the plane normal n. The line-plane angle is its complement, so use sin(theta)=|d dot n|/(|d||n|). Here d dot n = 2-2+4=4, |d|=3 and |n|=3, hence sin(theta)=4/9. Therefore theta=arcsin(4/9), about 26.4 degrees. The absolute value gives the acute angle convention. If you first find the angle with the normal, subtract it from 90 degrees.",
    ),
    (
        "m12", "DSP-ALG", "Matrices: keeping row transformations consistent",
        "When I use a row operation to solve a system with an augmented matrix, I sometimes lose track of whether I changed the coefficient matrix only or the constants too. Is there a reliable check?",
        DoubtThread.Category.SYLLABUS_TOPIC, DoubtThread.Status.RESOLVED,
        "Apply each elementary row operation to the entire augmented row, including the constant column. For example, R2 <- R2-2R1 changes every entry in row 2. Keep a short operation log beside the matrix, then substitute the final values into each original equation. If you are finding an inverse by [A|I] -> [I|A^-1], the same rule applies to both halves. A solution that fails even one original equation signals an arithmetic or transcription error.",
    ),
    (
        "e49", "DSP-PROB", "Binomial distribution: quick variance calculation",
        "For a binomial variable with 12 trials and success probability 1/3, I calculated the variance by summing all r-squared probabilities. Is there a faster route, and what should I use for q?",
        DoubtThread.Category.SYLLABUS_TOPIC, DoubtThread.Status.RESOLVED,
        "For X~Binomial(n,p), set q=1-p and use Var(X)=npq. Here n=12, p=1/3 and q=2/3, so Var(X)=12*(1/3)*(2/3)=8/3. The mean is np=4. The formula works because the trials are independent and share the same success probability. You only need the full probability table if the question asks for a particular probability such as P(X=4).",
    ),
    (
        "e90", "DSP-MOCK", "Planning time across the full-syllabus mock",
        "I lose too much time on the first long calculus question and then rush the final section. How should I plan a first pass without leaving questions unanswered?",
        DoubtThread.Category.ASSIGNMENT_HOMEWORK, DoubtThread.Status.OPEN,
        "Try a two-pass plan based on the mock's stated duration: first complete questions whose method is clear, and mark longer calculations to revisit. Keep a time checkpoint for each section and reserve a final review window. After your next attempt, share which section took longest and we can tune the split to your pace. Do not leave the final answer transfer to the last minute.",
    ),
    (
        "e23", "DSP-TRIG", "Choosing the right identity for a compound-angle equation",
        "I am stuck deciding whether to expand sin(3x+ x) directly or first use a multiple-angle identity. I keep getting expressions that are hard to solve. Is there a preferred first step?",
        DoubtThread.Category.SYLLABUS_TOPIC, DoubtThread.Status.OPEN,
        "First check the interval and any restrictions in the question. If the expression is sin(4x), a multiple-angle identity may keep the equation shorter; if it is a sum of separate sine and cosine terms, compound-angle expansion may be clearer. Write the original equation beside each transformed line and check candidate roots in the original expression. Post your interval and the next algebra step you tried, and I can point to the shorter route.",
    ),
)


class Command(BaseCommand):
    help = "Seed recruiter-demo notices, study resources, and student doubt discussions."

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        try:
            teacher_user = User.objects.get(username="teacher1", role=User.Role.TEACHER)
            teacher = TeacherProfile.objects.get(user=teacher_user)
            classes = {
                "Morning Batch": Class.objects.get(name="11", section="M"),
                "Evening Batch": Class.objects.get(name="11", section="E"),
            }
        except (User.DoesNotExist, TeacherProfile.DoesNotExist, Class.DoesNotExist) as exc:
            raise CommandError("Import the DSP roster before seeding community demo content.") from exc

        subjects = {code: Subject.objects.filter(code=code).first() for code, *_ in RESOURCES}
        if any(subject is None for subject in subjects.values()):
            raise CommandError("All six DSP subjects must exist before seeding community content.")

        notice_count = 0
        for batch_name, student_class in classes.items():
            for title, content in NOTICE_TOPICS:
                Notice.objects.update_or_create(
                    teacher=teacher, student_class=student_class,
                    title=f"{batch_name}: {title}", defaults={"content": content},
                )
                notice_count += 1

        resource_dir = Path(settings.MEDIA_ROOT) / "resources"
        resource_dir.mkdir(parents=True, exist_ok=True)
        resource_count = 0
        for code, filename, title, content in RESOURCES:
            path = resource_dir / filename
            path.write_text(content, encoding="utf-8")
            subject = subjects[code]
            for batch_name, student_class in classes.items():
                Resource.objects.update_or_create(
                    title=f"{title} ({batch_name})", student_class=student_class,
                    defaults={
                        "description": f"Revision resource for {subject.name}, prepared by D.S.P. Sir.",
                        "teacher": teacher,
                        "subject": subject,
                        "file": f"resources/{filename}",
                    },
                )
                resource_count += 1

        thread_count = 0
        reply_count = 0
        for username, subject_code, title, content, category, status, reply_content in THREADS:
            try:
                student = StudentProfile.objects.select_related("user", "student_class").get(
                    user__username=username
                )
            except StudentProfile.DoesNotExist as exc:
                raise CommandError(f"Required demo student {username!r} is missing from the roster.") from exc
            thread, _ = DoubtThread.objects.update_or_create(
                student=student, title=title,
                defaults={
                    "content": content,
                    "category": category,
                    "is_public": True,
                    "student_class": student.student_class,
                    "subject": subjects[subject_code],
                    "status": status,
                },
            )
            reply = DoubtReply.objects.filter(thread=thread, user=teacher_user).first()
            if reply is None:
                DoubtReply.objects.create(
                    thread=thread, user=teacher_user, content=reply_content,
                    is_teacher_reply=True,
                )
            else:
                reply.content = reply_content
                reply.is_teacher_reply = True
                reply.save(update_fields=["content", "is_teacher_reply"])
            thread_count += 1
            reply_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"DSP community content ready: {notice_count} notices, {resource_count} study resources, "
            f"{thread_count} doubt threads, {reply_count} teacher replies."
        ))
