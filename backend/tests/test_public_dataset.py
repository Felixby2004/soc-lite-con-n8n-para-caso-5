import shutil

import pytest

from app.models.enums import SeverityLevel
from app.services.public_dataset_service import DATA_DIR, load_source, parse_line


def test_official_sample_integrity_and_complete_parse():
    manifest, lines = load_source()
    assert len(lines) == manifest['records'] == 2000
    parsed = [parse_line(line) for line in lines]
    assert all(event['host'] == 'LabSZ' for event in parsed)
    # La muestra conserva horas originales, no un año o zona horaria inferidos.
    assert parsed[0]['timestamp'] == 'Dec 10 06:55:46'


def test_failed_password_keeps_observed_identity_without_attack_verdict():
    _, lines = load_source()
    event = parse_line(lines[5])
    assert event['event_type'] == 'authentication_failed'
    assert event['username'] == 'webmaster'
    assert event['source_ip'] == '173.234.31.186'
    assert event['severity'] == SeverityLevel.MEDIUM
    assert 'verdict' not in event


def test_integrity_failure_rejects_modified_data(tmp_path):
    for name in ('manifest.json', 'OpenSSH_2k.log'):
        shutil.copyfile(DATA_DIR / name, tmp_path / name)
    with (tmp_path / 'OpenSSH_2k.log').open('ab') as stream:
        stream.write(b'changed')
    with pytest.raises(ValueError, match='SHA-256'):
        load_source(tmp_path)


def test_malformed_line_is_not_silently_imported():
    with pytest.raises(ValueError, match='Formato'):
        parse_line('not a real OpenSSH record')
