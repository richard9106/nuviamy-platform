"""Only opaque room/role identifiers leave Django. No media capture permissions."""
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


def client(region):
    return boto3.client('chime-sdk-meetings', region_name=region,
        config=Config(connect_timeout=3, read_timeout=5, retries={'total_max_attempts': 2}))


def absent(error):
    return isinstance(error, ClientError) and error.response.get('Error', {}).get('Code') in {'NotFoundException', 'NotFound'}


def create(region, media_region, fingerprint):
    return client(region).create_meeting(ClientRequestToken=fingerprint,
        ExternalMeetingId='nuvia-'+fingerprint[:40], MediaRegion=media_region,
        MeetingFeatures={'Attendee': {'MaxCount': 2}, 'Video': {'MaxResolution': 'HD'},
                         'Content': {'MaxResolution': 'None'}},
        Tags=[{'Key': 'Application', 'Value': 'NuviaMyTelehealth'}])['Meeting']


def terminate(room):
    if not room.external_room_id:
        return
    try:
        client(room.control_region).delete_meeting(MeetingId=room.external_room_id)
    except ClientError as error:
        if not absent(error):
            raise


def role_id(room, role):
    return 'nuvia-'+room.appointment_fingerprint[:32]+'-'+role


def revoke_role(room, role):
    if not room.external_room_id:
        return
    api = client(room.control_region)
    try:
        page = api.list_attendees(MeetingId=room.external_room_id)
        # The meeting is capped at two people. Never expose this response to a browser/log.
        for attendee in page.get('Attendees', []):
            if attendee.get('ExternalUserId') == role_id(room, role):
                try:
                    api.delete_attendee(MeetingId=room.external_room_id, AttendeeId=attendee['AttendeeId'])
                except ClientError as error:
                    if not absent(error):
                        raise
    except ClientError as error:
        if not absent(error):
            raise


def issue(room, role):
    # Rotation also revokes a token whose create response was lost in transit.
    revoke_role(room, role)
    return client(room.control_region).create_attendee(MeetingId=room.external_room_id,
        ExternalUserId=role_id(room, role),
        Capabilities={'Audio': 'SendReceive', 'Video': 'SendReceive', 'Content': 'None'})['Attendee']
