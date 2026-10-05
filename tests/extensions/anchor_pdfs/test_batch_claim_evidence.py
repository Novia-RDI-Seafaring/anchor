"""Approved suggestions use the same source preparation as direct writes."""
from copy import deepcopy

import pytest

from anchor.adapters.project_runtime import bind_workspace_sources
from anchor.core.events.actor import Actor
from anchor.core.services.workspace_batch import BatchApplyError
from anchor.core.services.workspace_service import WorkspaceService
from anchor.extensions.anchor_pdfs.infra.memory_doc_store import MemoryDocStore
from anchor.infra.bus.memory_bus import MemoryEventBus
from anchor.infra.stores.memory_stores import MemoryWorkspaceStore
from tests.adapters.test_value_provenance_parity import _input, _regions


@pytest.mark.parametrize('invalid_tail', [False, True])
async def test_batch_prepares_claims_before_emission_and_preserves_atomic_failure(invalid_tail):
    docs = MemoryDocStore()
    await docs.write_gold_region_file('doc', 1, _regions())
    ws = WorkspaceService(MemoryWorkspaceStore(), MemoryEventBus())
    bind_workspace_sources(ws, docs)
    await ws.create_workspace('batch')
    data = _input('exact')
    edited = deepcopy(data)
    edited['rows'][0]['value'] = '999999'
    ops = [
        {'type': 'NodeAdded', 'payload': {'id': 'spec', 'node_type': 'spec', 'data': data}},
        {'type': 'NodeUpdated', 'payload': {'id': 'spec', 'fields': {'data': edited}}},
    ]
    if invalid_tail:
        ops.append({'type': 'NodeRemoved', 'payload': {'id': 'missing'}})
    kwargs = dict(actor=Actor(kind='agent', label='test'), causation_id='suggestion',
                  approver=Actor(kind='human', label='reviewer'))
    if invalid_tail:
        before = await ws.get_state('batch')
        with pytest.raises(BatchApplyError):
            await ws.apply_batch('batch', ops, **kwargs)
        assert await ws.get_state('batch') == before
        return
    state, events, ids = await ws.apply_batch('batch', ops, **kwargs)
    added = events[0].payload['data']['rows'][0]
    changed = events[1].payload['fields']['data']['rows'][0]
    assert added['evidence']['status'] == 'verified'
    assert added['source_ref']['coord_origin'] == 'top-left'
    assert changed['evidence']['status'] == 'stale'
    assert state.nodes[ids['spec']].data['rows'][0] == changed
    assert all(event.actor == kwargs['actor'] for event in events)
    assert state.nodes[ids['spec']].data['review']['state'] == 'accepted'
    revalidate = deepcopy(data)
    revalidate['rows'][0]['revalidate_evidence'] = True
    state, events, _ = await ws.apply_batch('batch', [{
        'type': 'NodeUpdated', 'payload': {'id': ids['spec'], 'fields': {'data': revalidate}},
    }], **kwargs)
    assert state.nodes[ids['spec']].data['rows'][0]['evidence']['status'] == 'verified'
