"""Versioned English screeners. Preserve published item/choice wording and scoring.

Sources and reproduction permissions: docs/product/scored-measures.md.
Never infer a diagnosis or suicide risk from a summed score.
"""
from copy import deepcopy

OPTIONS = ('Not at all', 'Several days', 'More than half the days', 'Nearly every day')
ATTRIBUTION = ('Developed by Drs. Robert L. Spitzer, Janet B.W. Williams, Kurt Kroenke and colleagues, '
               'with an educational grant from Pfizer Inc. No permission required to reproduce, translate, display or distribute.')
DEFINITIONS = {
    'phq9_en_v1': {
        'name': 'PHQ-9', 'maximum': 27, 'topic': 'Depressive symptoms',
        'source': 'https://www.camh.ca/-/media/files/phq-9_english-pdf.pdf',
        'instruction': 'Over the last 2 weeks, how often have you been bothered by any of the following problems?',
        'items': (
            'Little interest or pleasure in doing things',
            'Feeling down, depressed, or hopeless',
            'Trouble falling or staying asleep, or sleeping too much',
            'Feeling tired or having little energy',
            'Poor appetite or overeating',
            'Feeling bad about yourself — or that you are a failure or have let yourself or your family down',
            'Trouble concentrating on things, such as reading the newspaper or watching television',
            'Moving or speaking so slowly that other people could have noticed? Or the opposite — being so fidgety or restless that you have been moving around a lot more than usual',
            'Thoughts that you would be better off dead or of hurting yourself in some way',
        ),
        'bands': ((0, 'Minimal'), (5, 'Mild'), (10, 'Moderate'), (15, 'Moderately severe'), (20, 'Severe')),
    },
    'gad7_en_v1': {
        'name': 'GAD-7', 'maximum': 21, 'topic': 'Anxiety symptoms',
        'source': 'https://www.camh.ca/-/media/files/gad-7_english-pdf.pdf',
        'instruction': 'Over the last 2 weeks, how often have you been bothered by the following problems?',
        'items': (
            'Feeling nervous, anxious or on edge',
            'Not being able to stop or control worrying',
            'Worrying too much about different things',
            'Trouble relaxing',
            'Being so restless that it is hard to sit still',
            'Becoming easily annoyed or irritable',
            'Feeling afraid as if something awful might happen',
        ),
        'bands': ((0, 'Minimal'), (5, 'Mild'), (10, 'Moderate'), (15, 'Severe')),
    },
}
MEASURE_CHOICES = tuple((code, f"{definition['name']} · English · Adults") for code, definition in DEFINITIONS.items())
DIFFICULTY_LABEL = ('If you checked off any problems, how difficult have these problems made it for you to do your work, '
                    'take care of things at home, or get along with other people?')
DIFFICULTY_OPTIONS = ('Not difficult at all', 'Somewhat difficult', 'Very difficult', 'Extremely difficult')


def questions_for(code):
    definition = DEFINITIONS[code]
    questions = [{'_builder_version': 1, 'id': f'{code}-{index+1}', 'label': label,
        'type': 'single_choice', 'required': True, 'options': list(OPTIONS), 'help_text': '',
        'page_id': code, 'page_title': definition['name'], 'page_description': definition['instruction']}
        for index, label in enumerate(definition['items'])]
    if code == 'phq9_en_v1':
        questions.append({'_builder_version': 1, 'id': code+'-difficulty', 'label': DIFFICULTY_LABEL,
            'type': 'single_choice', 'required': False, 'options': list(DIFFICULTY_OPTIONS), 'help_text': '',
            'page_id': code, 'page_title': definition['name'], 'page_description': ''})
    return deepcopy(questions)


def score_assignment(assignment):
    """Only complete, submitted, unmodified standard versions can produce scores."""
    snapshot = assignment.template_snapshot or {}
    code = snapshot.get('measure_code')
    definition = DEFINITIONS.get(code) if isinstance(code, str) else None
    if (not definition or assignment.status not in ('submitted', 'reviewed') or not assignment.submitted_at
            or snapshot.get('questions') != questions_for(code) or not isinstance(assignment.answers, dict)):
        return None
    values = []
    for index in range(len(definition['items'])):
        value = assignment.answers.get(f'question_{index}')
        value = value.get('answer') if isinstance(value, dict) else value
        if value not in OPTIONS:
            return None
        values.append(OPTIONS.index(value))
    total = sum(values)
    band = next(label for threshold, label in reversed(definition['bands']) if total >= threshold)
    return {'code': code, 'name': definition['name'], 'total': total, 'maximum': definition['maximum'],
            'band': band, 'item9_endorsed': code == 'phq9_en_v1' and values[8] > 0}


def chart_series(assignments):
    """Separate raw-score scales; time spacing reflects actual submission dates."""
    series = []
    for code, definition in DEFINITIONS.items():
        rows = []
        for assignment in assignments:
            score = score_assignment(assignment)
            if score and score['code'] == code:
                rows.append({'assignment': assignment, 'score': score})
        rows.sort(key=lambda row: (row['assignment'].submitted_at, row['assignment'].pk))
        points = []
        if rows:
            start = rows[0]['assignment'].submitted_at.timestamp()
            duration = rows[-1]['assignment'].submitted_at.timestamp() - start
            for row in rows:
                x = 36 + (row['assignment'].submitted_at.timestamp()-start) / duration * 528 if duration else 300
                y = 160 - row['score']['total'] / definition['maximum'] * 132
                row.update(x=f'{x:.2f}', y=f'{y:.2f}')
                points.append(f'{x:.2f},{y:.2f}')
        series.append({'code': code, 'name': definition['name'], 'topic': definition['topic'],
            'maximum': definition['maximum'], 'rows': list(reversed(rows)), 'latest': rows[-1] if rows else None,
            'points': ' '.join(points), 'first_date': rows[0]['assignment'].submitted_at if rows else None})
    return series
