from django.urls import path
from .views import RagQueryView

app_name = 'rag_engine'

urlpatterns = [
    path('', RagQueryView.as_view(), name='rag-query'),
]
