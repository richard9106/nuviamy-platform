import json
import hashlib
import zipfile
from datetime import datetime
from html import escape
from io import BytesIO
from uuid import UUID

from django.http import HttpResponse
from django.core.exceptions import SuspiciousFileOperation
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from botocore.exceptions import BotoCoreError, ClientError
from .export_schema import EXPORT_FIELDS
from .models import UserProfile
from .contract_models import StandardAgreementAcceptance, ClinicalContractRequest, ClinicalContractBundle, ClinicalContractSignature
from apps.practices.models import TherapistProfile
from apps.appointments.models import PracticeWorkingHour, PracticeAvailabilityOverride

from apps.appointments.models import Appointment
from apps.audit.models import AuditLog
from apps.billing.models import Invoice, Payment, ServicePackage, InsurancePayer, InsuranceRate, PracticeInsurancePayer, SessionPackageTemplate, PackageUsage
from apps.clients.models import Client
from apps.clinical.models import Diagnosis, SessionNote, SessionNoteSignature, SessionNoteAddendum, TreatmentPlan
from apps.dashboard.models import Task
from apps.documents.models import ClientDocument
from apps.portal.models import (ClientPortalAccess, ClientPortalRequest, PortalConversation, PortalMessage,
    PublicBookingRequest, IntakePacketTemplate, ClientIntakeAssignment)


def _rows(queryset, *fields):
    return list(queryset.values(*fields))


def _download_response(content, content_type, filename):
    response = HttpResponse(content.getvalue(), content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def _records(queryset):
    return _rows(queryset, *EXPORT_FIELDS[queryset.model._meta.label])


def build_export_data(practice, scope):
    if scope not in {'all', 'clinical', 'billing'}:
        raise ValueError('Unknown export scope.')
    data = {'scope': scope, 'practice': {name: getattr(practice, name) for name in (
        'id', 'name', 'practice_type', 'email', 'phone', 'address_line1', 'address_line2',
        'city', 'state', 'postal_code', 'description')}}
    sections = {}
    if scope in {'all', 'clinical'}:
        sections.update({
            'clients': Client.objects.filter(practice=practice),
            'appointments': Appointment.objects.filter(practice=practice),
            'diagnoses': Diagnosis.objects.filter(practice=practice),
            'treatment_plans': TreatmentPlan.objects.filter(practice=practice),
            'session_notes': SessionNote.objects.filter(practice=practice),
            'session_note_signatures': SessionNoteSignature.objects.filter(note__practice=practice),
            'session_note_addenda': SessionNoteAddendum.objects.filter(note__practice=practice),
            'documents': ClientDocument.objects.filter(practice=practice),
            'portal_access': ClientPortalAccess.objects.filter(practice=practice),
            'portal_requests': ClientPortalRequest.objects.filter(practice=practice),
            'portal_conversations': PortalConversation.objects.filter(practice=practice),
            'portal_messages': PortalMessage.objects.filter(practice=practice, conversation__practice=practice),
            'public_booking_requests': PublicBookingRequest.objects.filter(practice=practice),
            'intake_templates': IntakePacketTemplate.objects.filter(practice=practice),
            'intake_assignments': ClientIntakeAssignment.objects.filter(practice=practice),
        })
    if scope in {'all', 'billing'}:
        sections.update({
            'invoices': Invoice.objects.filter(practice=practice),
            'payments': Payment.objects.filter(practice=practice),
            'service_packages': ServicePackage.objects.filter(practice=practice),
            'session_package_templates': SessionPackageTemplate.objects.filter(practice=practice),
            'package_usages': PackageUsage.objects.filter(package__practice=practice, appointment__practice=practice),
            'insurance_rates': InsuranceRate.objects.filter(practice=practice),
            'payer_selections': PracticeInsurancePayer.objects.filter(practice=practice),
        })
    relevant = InsurancePayer.objects.filter(Q(practice=practice) | Q(practice_selections__practice=practice)
        | Q(insured_clients__practice=practice) | Q(invoices__practice=practice) | Q(rates__practice=practice))
    sections['insurance_payers'] = relevant.filter(Q(practice=practice) | Q(practice__isnull=True)).distinct()
    if scope == 'all':
        sections.update({
            'tasks': Task.objects.filter(practice=practice),
            'audit_logs': AuditLog.objects.filter(practice=practice),
            'therapists': TherapistProfile.objects.filter(practice=practice),
            'working_hours': PracticeWorkingHour.objects.filter(practice=practice),
            'availability_overrides': PracticeAvailabilityOverride.objects.filter(practice=practice),
            'standard_agreements': StandardAgreementAcceptance.objects.filter(practice=practice),
            'contract_requests': ClinicalContractRequest.objects.filter(practice=practice),
            'contract_bundles': ClinicalContractBundle.objects.filter(request__practice=practice),
            'contract_signatures': ClinicalContractSignature.objects.filter(bundle__request__practice=practice),
        })
        data['team_profiles'] = _rows(UserProfile.objects.filter(practice=practice),
            'id', 'user_id', 'practice_id', 'role', 'phone', 'permissions', 'profile_photo', 'created_at', 'updated_at')
    if scope in {'all', 'clinical'}:
        # Resolve authors without exporting passwords, MFA or other account secrets.
        staff = get_user_model().objects.filter(Q(nuvia_profile__practice=practice)
            | Q(therapist_profile__practice=practice)).distinct()
        data['team_members'] = _rows(staff, 'id', 'first_name', 'last_name', 'email', 'is_active')
        data['therapists'] = _records(TherapistProfile.objects.filter(practice=practice))
    data.update({name: _records(queryset.order_by('pk')) for name, queryset in sections.items()})
    return data


class ExportFileUnavailable(Exception):
    """An archive must not silently omit a file referenced by the selected records."""


def _export_files(practice, scope, data):
    # Iterate the captured record list, not a second database query with different rows.
    if scope in {'all', 'clinical'}:
        for row in data['documents']:
            yield 'documents', row['id'], row['file'], ClientDocument._meta.get_field('file').storage
        for row in data['clients']:
            if row['profile_photo']:
                yield 'client-photos', row['id'], row['profile_photo'], Client._meta.get_field('profile_photo').storage
    if scope == 'all':
        for row in data['team_profiles']:
            if row['profile_photo']:
                yield 'team-photos', row['id'], row['profile_photo'], UserProfile._meta.get_field('profile_photo').storage


def build_zip_export(practice, scope, data):
    archive = BytesIO()
    manifest = {'schema_version': 2, 'scope': scope, 'created_at': timezone.now().isoformat(),
                'record_counts': {key: len(value) for key, value in data.items() if isinstance(value, list)},
                'files': [], 'excluded': ['Authentication secrets and OAuth tokens',
                    'Private product-support conversations', 'Provider-side data and historic object versions',
                    'Backups and platform-only security records']}
    records = json.dumps(data, default=str, indent=2).encode('utf-8')
    manifest['records'] = {'path': 'practice-data.json', 'bytes': len(records),
                           'sha256': hashlib.sha256(records).hexdigest()}
    try:
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr('practice-data.json', records)
            for category, record_id, name, storage in _export_files(practice, scope, data):
                if not name:
                    raise ExportFileUnavailable('A selected file is unavailable.')
                # No user-controlled filename or storage path becomes an archive entry.
                path = f'{category}/{record_id}'
                digest = hashlib.sha256()
                size = 0
                try:
                    with storage.open(name, 'rb') as source, bundle.open(path, 'w') as destination:
                        while chunk := source.read(64 * 1024):
                            destination.write(chunk)
                            digest.update(chunk)
                            size += len(chunk)
                except (OSError, SuspiciousFileOperation, BotoCoreError, ClientError) as error:
                    raise ExportFileUnavailable('A selected file is unavailable.') from error
                manifest['files'].append({'category': category, 'record_id': record_id, 'path': path,
                                          'bytes': size, 'sha256': digest.hexdigest()})
            bundle.writestr('manifest.json', json.dumps(manifest, indent=2))
            bundle.writestr('README.txt', EXPORT_README)
        archive.seek(0)
        return _download_response(archive, 'application/zip', f'nuviamy-{practice.pk}-export.zip')
    finally:
        archive.close()


EXPORT_README = '''NuviaMy practice return archive (schema 2)
Confidential: store on an encrypted device and share only through an approved channel.
practice-data.json contains records for the selected scope. manifest.json lists record
counts, maps file entries to their source records and includes SHA-256 hashes of the
captured JSON and file bytes. Verify these hashes and record counts before accepting
return. Hashes detect changes after capture; they do not authenticate the sender or
prove a coherent snapshot across simultaneous edits. Coordinate a quiet export window.
Document titles and original names are in JSON; archive file paths use record IDs.
PDF/SVG are summaries; Excel has data tables, without binary files. This ZIP does not
include provider-side records, old object versions, backups, authentication secrets,
platform-only security records or private product-support conversations. It is not a
patient access-response bundle: review third-party information and clinical access
rules before disclosing to a patient. No automatic import into another EHR is provided.
Export does not cancel, erase, anonymize, or change records. Cancellation alone does
not authorize deletion. Arrange an authenticated closure review for retention duties,
legal holds, active data, object versions, backups and prevention of reintroduction
on restore. Do not email clinical records to product support.
'''


def _cell_value(value):
    if isinstance(value, str) and value.startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
        return "'" + value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    if isinstance(value, datetime) and value.tzinfo:
        return value.replace(tzinfo=None)
    return value


def build_excel_export(practice, scope, data):
    from openpyxl import Workbook

    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, rows in data.items():
        if not isinstance(rows, list):
            rows = [rows]
        sheet = workbook.create_sheet(name[:31] or 'Export')
        if not rows:
            sheet.append(['No records'])
            continue
        headers = list(rows[0].keys()) if isinstance(rows[0], dict) else ['value']
        sheet.append(headers)
        for row in rows:
            sheet.append([_cell_value(row.get(header)) if isinstance(row, dict) else _cell_value(row) for header in headers])
        sheet.freeze_panes = 'A2'
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = min(max(len(str(cell.value or '')) for cell in column) + 2, 42)
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return _download_response(output, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', f'nuviamy-{practice.pk}-export.xlsx')


def build_pdf_export(practice, scope, data):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=landscape(letter), rightMargin=0.4 * inch, leftMargin=0.4 * inch, topMargin=0.4 * inch, bottomMargin=0.4 * inch)
    styles = getSampleStyleSheet()
    story = [Paragraph('NuviaMy Practice Data Export', styles['Title']), Paragraph(f'{escape(practice.name)} · Scope: {escape(scope)}', styles['Normal']), Spacer(1, 12)]
    story.append(Paragraph('Summary preview: up to 1,000 rows per section and 500 characters per field. Download the ZIP export for complete records and documents.', styles['Normal']))
    for name, rows in data.items():
        story.append(Paragraph(name.replace('_', ' ').title(), styles['Heading2']))
        if isinstance(rows, dict):
            rows = [rows]
        if not rows:
            story.append(Paragraph('No records', styles['Normal']))
        else:
            headers = list(rows[0].keys()) if isinstance(rows[0], dict) else ['value']
            table_rows = [[Paragraph(str(header), styles['Heading4']) for header in headers]]
            for row in rows[:1000]:
                table_rows.append([Paragraph(escape(str(_cell_value(row.get(header) if isinstance(row, dict) else row))[:500]), styles['BodyText']) for header in headers])
            table = Table(table_rows, repeatRows=1)
            table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7052D9')), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white), ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#CBD5E1')), ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
            story.extend([table, Spacer(1, 10)])
    document.build(story)
    output.seek(0)
    return _download_response(output, 'application/pdf', f'nuviamy-{practice.pk}-export.pdf')


def build_svg_export(practice, scope, data):
    rows = [(name.replace('_', ' ').title(), len(value) if isinstance(value, list) else 1) for name, value in data.items() if name != 'practice']
    height = 150 + max(len(rows), 1) * 34
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="{height}" viewBox="0 0 900 {height}">', '<rect width="100%" height="100%" fill="#F8F9FB"/>', '<text x="40" y="58" font-family="Arial, sans-serif" font-size="28" font-weight="700" fill="#1F2937">NuviaMy Practice Summary</text>', f'<text x="40" y="88" font-family="Arial, sans-serif" font-size="15" fill="#64748B">{escape(practice.name)} · {escape(scope)} export</text>']
    for index, (label, count) in enumerate(rows):
        y = 130 + index * 34
        parts.append(f'<text x="50" y="{y}" font-family="Arial, sans-serif" font-size="15" fill="#475569">{escape(label)}</text><text x="820" y="{y}" text-anchor="end" font-family="Arial, sans-serif" font-size="15" font-weight="700" fill="#7052D9">{count}</text>')
    parts.append('</svg>')
    return HttpResponse(''.join(parts), content_type='image/svg+xml', headers={'Content-Disposition': f'attachment; filename="nuviamy-{practice.pk}-summary.svg"'})


def build_practice_export(practice, scope, export_format='zip'):
    data = build_export_data(practice, scope)
    if export_format == 'xlsx':
        return build_excel_export(practice, scope, data)
    if export_format == 'pdf':
        return build_pdf_export(practice, scope, data)
    if export_format == 'svg':
        return build_svg_export(practice, scope, data)
    return build_zip_export(practice, scope, data)
