from django.shortcuts import render

# web/nl2sql_app/views.py
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .langgraph_agent import run_nl_query

@csrf_exempt
def nl_query(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    payload = json.loads(request.body)
    question = payload.get("question")
    if not question:
        return JsonResponse({"error": "no question provided"}, status=400)

    state = run_nl_query(question)
    return JsonResponse(state, safe=False)
