"""Public guides for therapists who run a private practice."""

from django.http import Http404
from django.shortcuts import render


ARTICLES = {
    "private-practice-checklist-for-therapists": {
        "title": "Private Practice Checklist for Therapists",
        "description": "Set up your scheduling, intake, notes, and billing workflows, then test the first-client experience with a fictional appointment.",
        "category": "Starting a practice",
        "product_url": "therapy_practice_management",
        "product_label": "Explore NuviaMy for private practice",
        "body": "marketing/blog/private_practice_checklist.html",
    },
    "therapy-progress-note-template": {
        "title": "Therapy Progress Note Template and Example",
        "description": "Use this copyable documentation outline and a fictional example to set up a consistent progress note workflow for your practice.",
        "category": "Clinical documentation",
        "product_url": "clinical_notes_software",
        "product_label": "See how to write and find notes in NuviaMy",
        "body": "marketing/blog/progress_note_template.html",
    },
    "therapy-intake-checklist": {
        "title": "Therapy Intake Checklist for a First Appointment",
        "description": "Prepare a clear intake process, from sending forms to checking what has been returned before a client's first appointment.",
        "category": "Client onboarding",
        "product_url": "client_portal_software",
        "product_label": "Explore the NuviaMy client portal and forms",
        "body": "marketing/blog/therapy_intake_checklist.html",
    },
}


def blog_index(request):
    return render(request, "marketing/blog/index.html", {"articles": ARTICLES})


def blog_article(request, slug):
    article = ARTICLES.get(slug)
    if article is None:
        raise Http404
    return render(request, "marketing/blog/article.html", {
        "article": article,
        "seo_title": f"{article['title']} | NuviaMy",
        "related_articles": {
            key: value for key, value in ARTICLES.items() if key != slug
        },
    })
