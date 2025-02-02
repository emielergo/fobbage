"""
The different models that together make out a quiz
"""
import random

from django.db import models
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .messages import session_updated

User = get_user_model()


class Quiz(models.Model):
    title = models.CharField(
        max_length=255,
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
    )

    def __str__(self):
        """ string representation """
        if self.title:
            return "Quiz: {}".format(self.title)
        else:
            return "Quiz: unnamed quiz"


class Question(models.Model):
    class Meta:
        ordering = ['order', 'id']

    text = models.CharField(
        max_length=255,
    )
    correct_answer = models.CharField(
        max_length=255,
    )
    quiz = models.ForeignKey(
        Quiz,
        related_name='questions',
        on_delete=models.CASCADE,
    )

    order = models.IntegerField()
    image_url = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )
    player = models.ForeignKey(
        User,
        related_name='questions',
        on_delete=models.CASCADE,
    )

    def __str__(self):
        """ string representation """
        return "Question: {}".format(self.text)


class Session(models.Model):
    # class Meta:

    quiz = models.ForeignKey(
        Quiz,
        related_name='sessions',
        on_delete=models.CASCADE,
    )
    created = models.DateField(auto_now=True)
    name = models.CharField(
        max_length=255,
    )
    owner = models.ForeignKey(
        User,
        related_name='hosting',
        on_delete=models.DO_NOTHING,
    )
    players = models.ManyToManyField(
        User,
        related_name='playing',
    )
    active_fobbit = models.ForeignKey(
        to='quizes.Fobbit',
        null=True,
        blank=True,
        default=None,
        on_delete=models.SET_NULL,
        related_name='active_in'
    )
    BLUFFING, GUESSING = range(2)
    MODI = [
        (BLUFFING, 'Bluffing'),
        (GUESSING, 'Guessing'),
    ]

    modus = models.IntegerField(
        choices=MODI,
        default=BLUFFING,
    )
    settings = models.JSONField(default=dict)

    def __str__(self):
        return self.name

    @property
    def rounds(self):
        try:
            return self.settings.get('rounds', [])
            # return rounds[self.settings.get('activeRound', 10)]
        except KeyError:
            return []

    @property
    def active_round(self):
        try:
            if self.active_fobbit:
                return self.active_fobbit.round
        except KeyError:
            return -1

        return -1

    def questions_in_round(self, round):
        # active round
        try:
            return self.rounds[round]['number_of_questions']
        except (IndexError, KeyError, TypeError):
            return 0

    # move to manager
    def next_question(self):
        # While bluffing, create a new fobbit out of available questions
        fobbit = None

        max_questions = self.questions_in_round(round=self.active_round)
        n_of_questions = self.fobbits.filter(round=self.active_round).count()

        if self.modus == self.BLUFFING:
            if n_of_questions < max_questions:
                fobbit = self.generate_fobbit(round=self.active_round)
            else:
                # Go back to guessing
                self.modus = self.GUESSING
                fobbit = self.fobbits.filter(round=self.active_round).first()

        if fobbit:
            self.active_fobbit = fobbit

        self.save()
        return fobbit

    # move to manager
    def generate_fobbit(self, round):
        questions = self.quiz.questions.exclude(
                id__in=[self.fobbits.values_list('question', flat=True)]
            )
        question = questions.first()

        return Fobbit.objects.create(
            question=question,
            session=self,
            round=round,
        )

    def new_round(self, round):
        rounds = self.rounds
        rounds.append(round)

        self.settings['rounds'] = rounds
        self.active_fobbit = self.generate_fobbit(round=len(rounds)-1)
        # return to guessing
        self.modus = 0
        self.save()

    def score_for_player(self, player):
        score = 0
        for fobbit in self.fobbits.all():
            score += fobbit.score_for_player(player)
        return score


class Fobbit(models.Model):
    """Combination of session and question"""

    class Meta:
        ordering = ['id']

    session = models.ForeignKey(
        Session,
        related_name='fobbits',
        on_delete=models.CASCADE,
    )

    question = models.ForeignKey(
        Question,
        related_name='fobbits',
        on_delete=models.CASCADE,
    )
    BLUFF, GUESS, FINISHED = range(3)
    STATUS_CHOICES = (
        (BLUFF, 'Bluff'),
        (GUESS, 'Guess'),
        (FINISHED, 'Finished'),
    )
    status = models.IntegerField(
        choices=STATUS_CHOICES,
        default=0
    )

    # integer, round details are stored in the session
    round = models.IntegerField(default=0)

    def __str__(self):
        return self.question.text

    @property
    def multiplier(self):
        # get the multiplier from the round
        if self.session.rounds:
            try:
                return self.session.rounds[self.round]['multiplier']
            except IndexError:
                return self.round + 1
        else:
            return 1

    @property
    def players_without_guess(self):
        return [
            player for player in self.session.players.all()
            if len(player.guesses.filter(answer__fobbit=self)) == 0]

    @property
    def players_without_bluff(self):
        return [
            player for player in self.session.players.all()
            if len(player.bluffs.filter(fobbit=self)) == 0]

    @property
    def scored_answers(self):
        if self.status == self.FINISHED:
            return self.answers.annotate(
                num_guesses=models.Count('guesses')
            ).order_by('is_correct', 'num_guesses')
        else:
            return self.answers.empty()

    def generate_answers(self):
        """
        Creates a new list of possible answers
        use a combination of bluffs and the correct answer
        """
        if len(self.session.players.all()) == 0:
            return False

        # Check if all players have bluffed
        if len(self.bluffs.all()) != len(self.session.players.all()):
            return False
        # Check if not already listed
        if self.status >= self.GUESS:
            return False

        for answer in self.answers.all():
            answer.delete()

        Answer.objects.create(
            fobbit=self,
            text=self.question.correct_answer,
            is_correct=True,
        )

        for bluff in self.bluffs.all():
            answer = self.answers.filter(text__iexact=bluff.text).first()
            if answer is None:
                answer = Answer.objects.create(
                    fobbit=self,
                    text=bluff.text)

            bluff.answer = answer
            bluff.save()

        answers = [answer for answer in self.answers.all()]
        random.shuffle(answers)
        i = 0
        for answer in answers:
            answer.order = i = i + 1
            answer.save()

        self.status = Fobbit.GUESS
        self.save()

        # TODO: go to next question
        # if status is addded before guess
        self.session.next_question()

    def score_for_player(self, player):
        score = 0
        # only finnished questions have scores
        if self.status != self.FINISHED:
            return 0

        player_bluff = self.bluffs.get(player=player)
        player_guess = Guess.objects.get(answer__fobbit=self, player=player)

        # als de speler heeft gebluffed
        if player_bluff:
            # 0 plunten als jouw bluff = correct antwoord
            if player_bluff.answer and player_bluff.answer.is_correct is True:
                return 0

            score += player_bluff.score

        # score voor juist antwoord
        if player_guess:
            if player_guess.answer == player_bluff.answer:
                return 0
            if player_guess.answer.text == self.question.correct_answer:
                score += player_guess.score

        return score

    def reset(self):
        self.status = Fobbit.BLUFF
        self.answers.all().delete()
        self.save()

    # FOBBIT
    def finish(self):
        """Finish the question if all players have guessed"""
        if len(self.players_without_guess) == 0:
            self.status = self.FINISHED
            self.save()
        else:
            raise Guess.DoesNotExist("Not all players have guessed")

    def delete_answers(self):
        if self.status < self.FINISHED:
            # self.guesses.delete()
            self.answers.all().delete()

            self.status = self.BLUFF
            self.save()
            return True


class Answer(models.Model):
    class Meta:
        ordering = ['order']

    fobbit = models.ForeignKey(
        Fobbit,
        related_name='answers',
        on_delete=models.CASCADE,
    )
    order = models.IntegerField(null=True)
    text = models.CharField(
        max_length=255,
    )
    showed = models.BooleanField(
        default=False,
    )
    is_correct = models.BooleanField(
        default=False
    )

    def __str__(self):
        """ string representation """
        return "{}: Answer {}".format(self.fobbit.question.text, self.order)


class Bluff(models.Model):
    text = models.CharField(
        max_length=255,
    )
    fobbit = models.ForeignKey(
        Fobbit,
        related_name='bluffs',
        on_delete=models.CASCADE,
    )
    player = models.ForeignKey(
        User,
        related_name='bluffs',
        on_delete=models.CASCADE,
    )
    answer = models.ForeignKey(
        Answer,
        related_name='bluffs',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    class Meta:
        unique_together = ("fobbit", "player"),

    @property
    def score(self):
        score = 0

        player_guess = Guess.objects.filter(
            answer__fobbit=self.fobbit,
            player=self.player).first()
        if player_guess:
            # 0 plunten als jouw bluff = correct antwoord
            if self.answer and self.answer.is_correct is True:
                return 0
            # 0 punten als je op je eigen antwoord stemt
            if player_guess.answer == self.answer:
                return 0

            # score voor anders spelers kiezen jouw bluff
            aantal_gepakt = len(Guess.objects.filter(answer=self.answer))

            score += (aantal_gepakt * self.fobbit.multiplier * 500) / len(
                Bluff.objects.filter(answer=self.answer))

        return score

    def __str__(self):
        """ string representation """
        return "{}: {}".format(self.player.first_name, self.text)


class Guess(models.Model):
    answer = models.ForeignKey(
        Answer,
        related_name='guesses',
        on_delete=models.CASCADE,
    )

    player = models.ForeignKey(
        User,
        related_name='guesses',
        on_delete=models.CASCADE,
    )

    @property
    def score(self):
        fobbit = self.answer.fobbit
        if fobbit.status == fobbit.FINISHED:
            if self.answer.text == fobbit.question.correct_answer:
                return fobbit.multiplier * 1000
        else:
            return 0


@receiver(post_save, sender=Session)
def session_updated_signal(sender, instance, created, **kwargs):
    session_updated(instance.id)


@receiver(post_save, sender=Fobbit)
def fobbit_updated_signal(sender, instance, created, **kwargs):
    session_updated(instance.session.id)


@receiver(post_save, sender=Bluff)
def bluff_updated_signal(sender, instance, created, **kwargs):
    session_updated(instance.fobbit.session.id)
    # everyone bluffed?
    if created:
        if len(instance.fobbit.bluffs.all()) == len(
                instance.fobbit.session.players.all()):
            instance.fobbit.generate_answers()


@receiver(post_save, sender=Guess)
def guess_updated_signal(sender, instance, created, **kwargs):
    session_updated(instance.answer.fobbit.session.id)


@receiver(post_save, sender=Answer)
def _updated_signal(sender, instance, created, **kwargs):
    session_updated(instance.fobbit.session.id)
