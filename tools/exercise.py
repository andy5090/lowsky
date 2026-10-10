"""Explicit, reversible scene-authoring branches; no physical defence model."""
import copy
import uuid

BRANCHES = [
    dict(id='continue', motion='continue', asset_state='unavailable', delay_ms=5000,
         label=dict(en='Continue flight', ko='비행 지속 분기'),
         description=dict(en='Keep the flight path; mark the selected facility unavailable for this exercise.',ko='비행 경로를 유지하고 선택한 시설을 훈련상 사용 중단으로 표시합니다.')),
    dict(id='hold', motion='hold', asset_state='restricted', delay_ms=5000,
         label=dict(en='Hold position', ko='제자리 대기 분기'),
         description=dict(en='Hold the selected aircraft at its scripted position; mark the facility restricted.',ko='선택한 비행체를 정해진 시점의 위치에 대기시키고 시설을 제한 운영으로 표시합니다.')),
    dict(id='withdraw', motion='withdraw', asset_state='available', delay_ms=5000,
         label=dict(en='Return along route', ko='경로 복귀 분기'),
         description=dict(en='Return along the existing fictional route; keep the facility available.',ko='기존 가상 경로를 되짚어 이동하며 시설은 사용 가능 상태를 유지합니다.')),
]


def sample(frames, at_ms):
    index = 0
    while index < len(frames)-2 and at_ms >= frames[index+1]['at_ms']:
        index += 1
    start, end = frames[index:index+2]
    ratio = max(0, min(1, (at_ms-start['at_ms'])/(end['at_ms']-start['at_ms'])))
    return [a+(b-a)*ratio for a,b in zip(start['position'],end['position'])]


def motion_time(selection, object_id, at_ms):
    if not selection or selection['object_id']!=object_id or at_ms < selection['effective_at_ms']:
        return at_ms
    if selection['branch_id']=='hold':
        return selection['effective_at_ms']
    if selection['branch_id']=='withdraw':
        return max(0, 2*selection['effective_at_ms']-at_ms)
    return at_ms


def apply_observations(payload, selection, world):
    if not selection:
        return payload
    # Change only already-received measurements, preserving timestamp/detection gates and source offsets.
    result=copy.deepcopy(payload)
    frames=world[selection['object_id']]
    for row in result['observations']:
        at=row['observed_at_ms']
        if row['object_id']!=selection['object_id'] or at < selection['effective_at_ms'] or 'position' not in row:
            continue
        old=sample(frames,at)
        new=sample(frames,motion_time(selection,row['object_id'],at))
        row['position']=[p+b-a for p,a,b in zip(row['position'],old,new)]
    return result


def view(layout, tracks, selection, at_ms):
    assets=[dict(id=b['id'],label=copy.deepcopy(b['label']),position=b['position'],
                 status='available',role=dict(en='Fictional facility',ko='가상 시설')) for b in layout['facilities']]
    assets.insert(0,dict(id='runway',label=dict(en='Runway',ko='활주로'),position=layout['runway']['center'],
                        status='available',role=dict(en='Fictional airfield surface',ko='가상 비행장 시설')))
    record=copy.deepcopy(selection)
    if record:
        record['status']='applied' if at_ms>=record['effective_at_ms'] else 'pending'
        if record['status']=='applied':
            branch=next(b for b in BRANCHES if b['id']==record['branch_id'])
            next(a for a in assets if a['id']==record['asset_id'])['status']=branch['asset_state']
    return dict(scope='scripted_training',assets=assets,eligible_objects=[t['object_id'] for t in tracks if not t['last_known']],
                branches=copy.deepcopy(BRANCHES),selection=record)


def select(command, state):
    if command.get('confirm') is not True or command.get('run_id')!=state['run_id']:
        raise ValueError('Confirm a branch for the current run')
    exercise=state['exercise']
    if exercise['selection']:
        raise ValueError('A branch is already selected; reset or start a new run')
    if command.get('object_id') not in exercise['eligible_objects']:
        raise ValueError('Choose a currently observed aircraft')
    if command.get('asset_id') not in {a['id'] for a in exercise['assets']}:
        raise ValueError('Unknown fictional facility')
    branch=next((b for b in BRANCHES if b['id']==command.get('branch_id')),None)
    if not branch or state['at_ms']+branch['delay_ms']>=state['duration_ms']:
        raise ValueError('Branch unavailable or scenario ending')
    return dict(id=uuid.uuid4().hex,run_id=state['run_id'],object_id=command['object_id'],asset_id=command['asset_id'],
                branch_id=branch['id'],selected_at_ms=state['at_ms'],effective_at_ms=state['at_ms']+branch['delay_ms'])
