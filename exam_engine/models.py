from django.db import models


class Question(models.Model):

    class QuestionType(models.TextChoices):
        MCQ_SINGLE = "MCQ_SINGLE", "MCQ - Single Correct"
        MCQ_MULTI = "MCQ_MULTI", "MCQ - Multiple Correct"
        TRUE_FALSE = "TRUE_FALSE", "True / False"
        NUMERICAL = "NUMERICAL", "Numerical"
        SHORT_ANSWER = "SHORT_ANSWER", "Short Answer"

    assessment = models.ForeignKey(
        "academics.Assessment",
        on_delete=models.CASCADE,
        related_name="questions"
    )

    question_text = models.TextField()

    question_type = models.CharField(
        max_length=20,
        choices=QuestionType.choices
    )

    marks = models.PositiveIntegerField(
        default=1
    )

    negative_marking = models.BooleanField(
        default=False
    )

    negative_marks = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0
    )

    # Correct answer for True/False,
    # Numerical and Short Answer questions.
    correct_answer = models.TextField(
        blank=True
    )

    # Used only when the test timing mode
    # is PER_QUESTION.
    time_limit_hours = models.PositiveIntegerField(
        default=0
    )

    time_limit_minutes = models.PositiveIntegerField(
        default=0
    )

    order = models.PositiveIntegerField(
        default=1
    )

    explanation = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.assessment.title} - Q{self.order}"


class QuestionOption(models.Model):

    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="options"
    )

    option_text = models.CharField(
        max_length=500
    )

    is_correct = models.BooleanField(
        default=False
    )

    order = models.PositiveIntegerField(
        default=1
    )

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.option_text


class QuestionImage(models.Model):

    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="images"
    )

    image = models.ImageField(
        upload_to="question_images/"
    )

    caption = models.CharField(
        max_length=200,
        blank=True
    )

    order = models.PositiveIntegerField(
        default=1
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"Image for {self.question}"


class AssessmentAttempt(models.Model):

    class Status(models.TextChoices):
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        SUBMITTED = "SUBMITTED", "Submitted"
        TIME_EXPIRED = "TIME_EXPIRED", "Time Expired"
        LOCKED = "LOCKED", "Locked"

    assessment = models.ForeignKey(
        "academics.Assessment",
        on_delete=models.CASCADE,
        related_name="attempts"
    )

    student = models.ForeignKey(
        "accounts.StudentProfile",
        on_delete=models.CASCADE,
        related_name="assessment_attempts"
    )

    started_at = models.DateTimeField()

    expires_at = models.DateTimeField()

    submitted_at = models.DateTimeField(
        null=True,
        blank=True
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "student"],
                name="unique_student_assessment_attempt"
            )
        ]

    def __str__(self):
        return f"{self.student} - {self.assessment.title}"


class StudentAnswer(models.Model):

    attempt = models.ForeignKey(
        AssessmentAttempt,
        on_delete=models.CASCADE,
        related_name="answers"
    )

    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="student_answers"
    )

    selected_option = models.ForeignKey(
        QuestionOption,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="single_answers"
    )

    selected_options = models.ManyToManyField(
        QuestionOption,
        blank=True,
        related_name="multiple_answers"
    )

    answer_text = models.TextField(
        blank=True
    )

    is_marked_for_review = models.BooleanField(
        default=False
    )

    awarded_marks = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True
    )

    answered_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "question"],
                name="unique_attempt_question_answer"
            )
        ]

    def __str__(self):
        return f"{self.attempt} - Q{self.question.order}"