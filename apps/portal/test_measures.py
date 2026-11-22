from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.accounts.export import build_export_data
from apps.clients.models import Client
from apps.practices.models import Practice
from .forms import IntakePacketTemplateForm
from .measures import DEFINITIONS, OPTIONS, chart_series, questions_for, score_assignment
from .models import ClientIntakeAssignment, ClientPortalAccess, IntakePacketTemplate


def answers_for(code, total):
    answers = {}
    for index in range(len(DEFINITIONS[code]['items'])):
        value = min(3, total)
        total -= value
        answers[f'question_{index}'] = {'answer': OPTIONS[value]}
    return answers


class ScoringTests(SimpleTestCase):
    def record(self, code='phq9_en_v1', total=0, **changes):
        values = dict(pk=1, status='submitted', submitted_at=timezone.now(),
                      template_snapshot={'measure_code': code, 'questions': questions_for(code)},
                      answers=answers_for(code, total))
        values.update(changes)
        return SimpleNamespace(**values)

    def test_every_score_and_range_boundary(self):
        for code, definition in DEFINITIONS.items():
            for total in range(definition['maximum'] + 1):
                with self.subTest(code=code,total=total):
                    score = score_assignment(self.record(code,total))
                    self.assertEqual(score['total'], total)
                    expected = [label for threshold,label in definition['bands'] if total >= threshold][-1]
                    self.assertEqual(score['band'],expected)

    def test_item9_is_independent_of_total_severity(self):
        record = self.record()
        record.answers['question_8']['answer'] = OPTIONS[1]
        result = score_assignment(record)
        self.assertEqual(result['total'],1)
        self.assertEqual(result['band'],'Minimal')
        self.assertTrue(result['item9_endorsed'])
        self.assertFalse(score_assignment(self.record(total=24))['item9_endorsed'])

    def test_no_estimated_score_for_draft_missing_invalid_or_modified_questions(self):
        record = self.record()
        for changes in [{'status':'assigned'}, {'submitted_at':None}, {'answers':{}}, {'answers':'invalid'},
                        {'template_snapshot':{'measure_code':'unknown'}},
                        {'template_snapshot':{'measure_code':[]}}]:
            self.assertIsNone(score_assignment(self.record(**changes)))
        record.answers['question_0'] = {'answer':'4'}
        self.assertIsNone(score_assignment(record))
        record = self.record()
        record.template_snapshot['questions'][0]['label'] = 'Modified item'
        self.assertIsNone(score_assignment(record))

    def test_functional_difficulty_is_not_added_to_phq_total(self):
        record = self.record(total=10)
        record.answers['question_9'] = {'answer':'Extremely difficult'}
        self.assertEqual(score_assignment(record)['total'],10)

    def test_chart_keeps_scales_separate_and_spaces_points_by_actual_time(self):
        start = timezone.now()
        rows = [self.record(total=5,pk=1,submitted_at=start),
                self.record(total=15,pk=2,submitted_at=start+timedelta(days=1)),
                self.record(total=10,pk=3,submitted_at=start+timedelta(days=10)),
                self.record('gad7_en_v1',20,pk=4,submitted_at=start)]
        phq, gad = chart_series(rows)
        self.assertEqual(phq['latest']['score']['total'],10)
        self.assertEqual(len(phq['rows']),3)
        self.assertAlmostEqual(float(phq['rows'][1]['x']),88.8)
        self.assertEqual(gad['maximum'],21)
        self.assertEqual(len(gad['rows']),1)


@override_settings(MFA_REQUIRED=False, MFA_PRIVILEGED_REQUIRED=False, EMAIL_TWO_STEP_REQUIRED=False)
class MeasureWorkflowTests(TestCase):
    def setUp(self):
        self.practice = Practice.objects.create(name='Fictional measure practice')
        self.other = Practice.objects.create(name='Other practice')
        self.owner = get_user_model().objects.create_user('measure-owner')
        UserProfile.objects.create(user=self.owner,practice=self.practice,role=UserProfile.Role.OWNER)
        self.patient = Client.objects.create(practice=self.practice,first_name='Fictional',last_name='Adult')
        self.patient_user = get_user_model().objects.create_user('measure-patient')
        UserProfile.objects.create(user=self.patient_user,practice=self.practice,role=UserProfile.Role.CLIENT)
        ClientPortalAccess.objects.create(practice=self.practice,client=self.patient,user=self.patient_user)
        self.client.force_login(self.owner)

    def add(self, code='phq9_en_v1'):
        response = self.client.post(reverse('intake:measure_add'),{'measure':code,'acknowledge':'on'})
        self.assertEqual(response.status_code,302)
        return IntakePacketTemplate.objects.get(practice=self.practice,measure_code=code)

    def assignment(self, **changes):
        template = self.add()
        values = dict(practice=self.practice,client=self.patient,template=template)
        values.update(changes)
        return ClientIntakeAssignment.objects.create(**values)

    def submit(self, assignment, item9=False):
        self.client.force_login(self.patient_user)
        data = {f'question_{index}':OPTIONS[0] for index in range(9)}
        if item9:
            data['question_8'] = OPTIONS[1]
        response = self.client.post(reverse('portal:intake_complete',args=[assignment.pk]),data)
        self.assertEqual(response.status_code,302)
        assignment.refresh_from_db()
        return assignment

    def test_library_import_is_scoped_idempotent_and_requires_acknowledgement(self):
        url = reverse('intake:measure_add')
        self.assertEqual(self.client.post(url,{'measure':'phq9_en_v1'}).status_code,200)
        self.assertFalse(IntakePacketTemplate.objects.exists())
        first = self.add()
        self.assertEqual(self.add().pk,first.pk)
        self.assertFalse(ClientIntakeAssignment.objects.exists())
        self.assertEqual(first.questions,questions_for('phq9_en_v1'))
        self.assertContains(self.client.get(url+'?_workspace_drawer=1'),'Standard measure')
        self.assertEqual(self.client.get(url+'?_workspace_drawer=1')['X-Frame-Options'],'SAMEORIGIN')

    def test_standard_template_content_cannot_be_edited_but_can_be_deactivated(self):
        template = self.add()
        original = deepcopy(template.questions)
        form = IntakePacketTemplateForm({'name':'Hacked','question_lines':'Different item','requires_signature':'on'},
                                        instance=template,practice=self.practice)
        self.assertTrue(form.is_valid(),form.errors)
        form.save()
        template.refresh_from_db()
        self.assertEqual(template.questions,original)
        self.assertFalse(template.active)
        self.assertFalse(template.requires_signature)
        self.assertNotEqual(template.name,'Hacked')

    def test_submitted_measure_is_scored_and_duplicate_portal_post_is_rejected(self):
        assignment = self.submit(self.assignment(),item9=True)
        self.assertEqual(assignment.measure_score['total'],1)
        self.assertTrue(assignment.measure_score['item9_endorsed'])
        response = self.client.post(reverse('portal:intake_complete',args=[assignment.pk]),{'question_0':OPTIONS[3]})
        self.assertEqual(response.status_code,404)
        assignment.refresh_from_db()
        self.assertEqual(assignment.measure_score['total'],1)

    def test_incomplete_draft_has_no_score_and_final_submit_requires_all_items(self):
        assignment = self.assignment()
        self.client.force_login(self.patient_user)
        url = reverse('portal:intake_complete',args=[assignment.pk])
        self.assertEqual(self.client.post(url,{'question_0':OPTIONS[3]}).status_code,200)
        self.assertEqual(self.client.post(url,{'question_0':OPTIONS[3],'action':'save_draft'}).status_code,302)
        assignment.refresh_from_db()
        self.assertIsNone(assignment.measure_score)

    def test_review_of_endorsed_item9_needs_explicit_confirmation(self):
        assignment = self.submit(self.assignment(),item9=True)
        self.client.force_login(self.owner)
        response_url = reverse('intake:responses',args=[assignment.pk])
        self.assertContains(self.client.get(response_url),'Item 9 endorsed')
        review_url = reverse('intake:review',args=[assignment.pk])
        self.client.post(review_url)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status,'submitted')
        self.client.post(review_url,{'item9_reviewed':'yes'})
        assignment.refresh_from_db()
        self.assertEqual(assignment.status,'reviewed')
        self.assertEqual(assignment.reviewed_by,self.owner)
        self.assertTrue(assignment.measure_score['item9_endorsed'])

    def test_client_chart_uses_only_its_submitted_measures_and_keeps_snapshot(self):
        assignment = self.submit(self.assignment())
        self.client.force_login(self.owner)
        template = assignment.template
        template.active=False
        template.save(update_fields=['active'])
        chart = self.client.get(reverse('clients:detail',args=[self.patient.pk])+'?tab=measures')
        self.assertContains(chart,'PHQ-9')
        self.assertEqual(chart.context['measure_series'][0]['latest']['score']['total'],0)
        self.assertIsNone(chart.context['measure_series'][1]['latest'])
        other_client = Client.objects.create(practice=self.practice,first_name='Another',last_name='Adult')
        empty = self.client.get(reverse('clients:detail',args=[other_client.pk])+'?tab=measures')
        self.assertIsNone(empty.context['measure_series'][0]['latest'])

    def test_foreign_practice_and_patient_cannot_access_measure_responses(self):
        assignment = self.assignment()
        foreign_client = Client.objects.create(practice=self.other,first_name='Foreign',last_name='Adult')
        foreign_template = IntakePacketTemplate.objects.create(practice=self.other,name='Foreign',questions=['Private'])
        foreign = ClientIntakeAssignment.objects.create(practice=self.other,client=foreign_client,template=foreign_template)
        self.assertEqual(self.client.get(reverse('intake:responses',args=[foreign.pk])).status_code,404)
        self.client.force_login(self.patient_user)
        self.assertEqual(self.client.get(reverse('portal:intake_complete',args=[foreign.pk])).status_code,404)
        self.assertNotEqual(self.client.get(reverse('intake:measure_add')).status_code,200)
        self.assertNotEqual(self.client.get(reverse('intake:responses',args=[assignment.pk])).status_code,200)

    def test_custom_template_named_phq9_is_never_automatically_scored(self):
        template = IntakePacketTemplate.objects.create(practice=self.practice,name='PHQ-9',questions=questions_for('phq9_en_v1'))
        assignment = ClientIntakeAssignment.objects.create(practice=self.practice,client=self.patient,template=template,
            answers=answers_for('phq9_en_v1',10),status='submitted',submitted_at=timezone.now())
        self.assertIsNone(assignment.measure_score)

    def test_results_are_in_clinical_exports_and_excluded_from_billing_exports(self):
        assignment = self.submit(self.assignment(),item9=True)
        data = build_export_data(self.practice,'clinical')
        self.assertEqual(len(data['measure_results']),1)
        self.assertEqual(data['measure_results'][0]['assignment_id'],assignment.pk)
        self.assertEqual(data['measure_results'][0]['total'],1)
        self.assertEqual(data['intake_templates'][0]['measure_code'],'phq9_en_v1')
        self.assertNotIn('measure_results',build_export_data(self.practice,'billing'))
        self.assertEqual(build_export_data(self.other,'clinical')['measure_results'],[])

    def test_intake_permission_alone_cannot_read_scores_or_review_measures(self):
        assignment = self.submit(self.assignment(),item9=True)
        user = get_user_model().objects.create_user('measure-intake-only')
        UserProfile.objects.create(user=user,practice=self.practice,role=UserProfile.Role.THERAPIST,
            permissions={'clinical':{'view':False},'intake':{'view':True,'edit':True,'create':True}})
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('intake:responses',args=[assignment.pk])).status_code,403)
        self.assertEqual(self.client.post(reverse('intake:review',args=[assignment.pk]),{'item9_reviewed':'yes'}).status_code,403)
        self.assertEqual(self.client.get(reverse('intake:measure_add')).status_code,403)
        queue = self.client.get(reverse('intake:list'))
        self.assertNotContains(queue,'Item 9 endorsed')
        self.assertNotContains(queue,'PHQ-9 1/27')
