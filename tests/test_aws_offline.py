import boto3
import pytest
from dose_check.agent import decide
from dose_check.speech import maybe_rephrase


@pytest.mark.parametrize('flag', [None, '0', 'auto', 'true'])
def test_global_aws_gate_blocks_calls_even_when_feature_flags_are_on(monkeypatch, flag):
    if flag is None:
        monkeypatch.delenv('AWS_ENABLED',raising=False)
    else:
        monkeypatch.setenv('AWS_ENABLED',flag)
    monkeypatch.setenv('AGENT_WITH_BEDROCK','1')
    monkeypatch.setenv('SPEAK_WITH_BEDROCK','1')
    calls = []
    def unexpected(*args, **kwargs):
        calls.append(args)
        raise AssertionError('AWS client or credential discovery attempted')
    monkeypatch.setattr(boto3,'client',unexpected)
    monkeypatch.setattr(boto3,'Session',unexpected)
    assert not decide("What's due now?",'older_adult',[],use_bedrock=True)['used_bedrock']
    assert maybe_rephrase({'speech':'Ready.'},'Ready.') == ('Ready.',False)
    assert calls == []


def test_auto_never_discovers_credentials(monkeypatch):
    monkeypatch.setenv('AWS_ENABLED','1')
    monkeypatch.setenv('AGENT_WITH_BEDROCK','auto')
    calls = []
    def unexpected(*args, **kwargs):
        calls.append(args)
        raise AssertionError('Automatic AWS access attempted')
    monkeypatch.setattr(boto3,'Session',unexpected)
    monkeypatch.setattr(boto3,'client',unexpected)
    assert not decide("What's due now?",'older_adult',[])['used_bedrock']
    assert calls == []
