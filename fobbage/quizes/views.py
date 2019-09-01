import json
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.shortcuts import render
from django.utils.safestring import mark_safe
from django.shortcuts import get_object_or_404
from django.db.models import Count
from django.views.generic import DetailView, ListView

from rest_framework import viewsets, generics
from rest_framework.response import Response

from .serializers import (
    QuizSerializer, BluffSerializer, AnswerSerializer,
    GuessSerializer, QuestionSerializer)
from .services import (
    generate_answers, score_for_quiz, score_for_bluff, )
from fobbage.quizes.models import (
    Quiz, Round, Question, Answer, Bluff, Guess, )

from .forms import NewQuizForm


def new_quiz(request):
    # if this is a POST request we need to process the form data
    if request.method == 'POST':
        # create a form instance and populate it with data from the request:
        form = NewQuizForm(request.POST)
        # check whether it's valid:
        if form.is_valid():
            # process the data in form.cleaned_data as required
            # ...
            quiz = Quiz.objects.create(
                title=form.cleaned_data['title'],
                created_by=request.user)

            Round.objects.create(
                title='Round 1',
                quiz=quiz,
            )
            # redirect to a new URL:
            return HttpResponseRedirect('/chat/{}/'.format(quiz.id))

    # if a GET (or any other method) we'll create a blank form
    else:
        form = NewQuizForm()

    return render(request, 'quizes/new.html', {'form': form})


def index(request):
    return render(request, 'quizes/index.html')


def room(request, room_name):
    return render(request, 'chat/room.html', {
        'room_name_json': mark_safe(json.dumps(room_name))
    })


def play(request):
    return render(request, 'quizes/play.html')


def quiz_view(request, quiz_id):
    quiz = Quiz.objects.get(pk=quiz_id)
    context = {
        'quiz': quiz,
    }

    question = quiz.active_question

    if quiz.active_question is not None:
        round = quiz.active_question.round
        context['question'] = question

        players = None
        if question.status == Question.BLUFF:
            players = question.players_without_bluff()
        elif question.status == Question.GUESS:
            players = question.players_without_guess()

        if players:
            context['players'] = players
        else:
            context['players'] = quiz.players.all()
    else:
        round = quiz.rounds.first()

    context['round'] = round

    return render(
        request, 'quizes/quiz.html', context)


def next_question(self, quiz_id):
    quiz = Quiz.objects.get(id=quiz_id)
    quiz.next_question()
    return HttpResponseRedirect(reverse('quiz', args=(quiz.id,)))


def prev_question(self, quiz_id):
    quiz = Quiz.objects.get(id=quiz_id)
    quiz.prev_question()
    return HttpResponseRedirect(reverse('quiz', args=(quiz.id,)))


def first_question(self, round):
    round = Round.objects.get(id=round)
    if round.first_question():
        return HttpResponseRedirect(reverse('quiz', args=(round.quiz.id,)))

    return HttpResponseRedirect(reverse('quiz', args=(round.quiz.id,)))


def collect_answers(request, question):
    question = Question.objects.get(pk=question)
    generate_answers(question.id)

    return HttpResponseRedirect(
        reverse('quiz', args=(question.round.quiz.id,)))


def hide_answers(request, question):
    question = Question.objects.get(pk=question)
    question.hide_answers()

    return HttpResponseRedirect(
        reverse('round', args=(question.round.id,)))


def start_guessing(request, round):
    round = Round.objects.get(pk=round)
    round.modus = Round.GUESSING
    round.save()

    round.active_question = round.questions.first()

    return HttpResponseRedirect(
        reverse('quiz', args=(round.quiz.id,)))


def show_scores(request, question):
    question = Question.objects.get(pk=question)
    if question.finish():
        # show player answers
        answer = Answer.objects \
            .filter(
                question=question,
                showed=False,
                is_correct=False) \
            .annotate(num_guesses=Count('guesses')) \
            .order_by('num_guesses') \
            .first()
        if answer:
            answer.showed = True
            answer.save()
        else:
            # reset answers to show again
            Answer.objects.filter(
                question=question).update(
                    showed=False)
            # show correct answer
            answer = Answer.objects.filter(
                question=question,
                is_correct=True).get()

        if answer:
            # bluffs en scores
            if len(answer.bluffs.all()) > 0:
                bluffs = [
                    {
                        'player': bluff.player,
                        'score': score_for_bluff(bluff.player, bluff)
                    } for bluff in answer.bluffs.all()
                ]
            else:
                bluffs = None
            # show the answer

            context = {
                'answer': answer,
                'bluffs': bluffs}
            return render(
                request, 'quizes/scores.html', context)

    return HttpResponseRedirect(
        reverse('quiz', args=(question.round.quiz.id,)))


def scoreboard(request, quiz_id):
    quiz = Quiz.objects.get(pk=quiz_id)
    active_question = quiz.active_question
    scores = {
        player: score_for_quiz(player, quiz)
        for player in quiz.players.all()
    }
    ranking = sorted(scores, key=scores.__getitem__, reverse=True)
    ranked_scores = [(player, scores[player]) for player in ranking]
    context = {
        'scores': ranked_scores,
        'active_question': active_question,
        'quiz': quiz,
    }
    return render(
        request, 'quizes/leaderboard.html', context)


class QuizDetail(DetailView):
    template_name = 'quizes/quiz_detail.html'
    model = Quiz

    def get_queryset(self):
        if self.request.user:
            return Quiz.objects.filter(created_by=self.request.user)
        else:
            return Quiz.objects.none()


class QuizList(ListView):
    template_name = 'quizes/quiz_list.html'
    model = Quiz

    def get_queryset(self):
        if self.request.user:
            return Quiz.objects.filter(created_by=self.request.user)
        else:
            return Quiz.objects.none()


# API
class QuizViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Quiz.objects.all()
    serializer_class = QuizSerializer


class AnswerViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Answer.objects.all()
    serializer_class = AnswerSerializer


class ActiveQuestionViewSet(viewsets.ModelViewSet):
    serializer_class = QuestionSerializer

    def get_queryset(self):
        return Question.objects.filter(
            id__in=Quiz.objects.values_list('active_question', flat=True))

    def retrieve(self, request, pk=None):
        question = get_object_or_404(Quiz, id=pk).active_question
        Quiz.objects.get(id=pk).active_question
        serializer = QuestionSerializer(question, context={'request': request})
        return Response(serializer.data)


class BluffViewSet(viewsets.ModelViewSet):
    serializer_class = BluffSerializer

    def get_queryset(self):
        if self.request.user:
            return Bluff.objects.filter(player=self.request.user)
        else:
            return Bluff.objects.none()

    def post(self, request, *args, **kwargs):
        return self.create(
            request, player=request.user, *args, **kwargs)


class GuessViewSet(viewsets.ModelViewSet):
    serializer_class = GuessSerializer

    def get_queryset(self):
        if self.request.user:
            return Guess.objects.filter(player=self.request.user)
        else:
            return Guess.objects.none()

    def post(self, request, *args, **kwargs):
        return self.create(
            request, player=request.user, *args, **kwargs)
