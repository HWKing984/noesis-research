"""Conservative span abstention from original BIO predictions; no label repair or lexicon."""
import train_course_ner as ner
import course_weak as c


def decode_with_abstention(labels, offsets, text):
    baseline = ner.decode_bio(labels, offsets, text)
    by_end = {e['end']:e for e in baseline['entities']}; reasons = {}
    key = lambda e: (e['start'],e['end'],e['label'])
    for i,(tag,offset) in enumerate(zip(labels,offsets)):
        if not i or tuple(offset)==(0,0) or not c.CONFIG['bioLabels'][tag].startswith('I-'): continue
        previous = tuple(offsets[i-1]); entity = by_end.get(previous[1])
        if previous!=(0,0) and entity and entity['start']<=previous[0]:
            reasons.setdefault(key(entity),[]).append('conflicting_I_continuation_after_closed_prefix')
    for e in baseline['entities']:
        start,end=e['start'],e['end']; word=lambda ch:ch.isalnum() or ch=='_'
        if (start and word(text[start-1]) and word(text[start])) or (end<len(text) and word(text[end-1]) and word(text[end])):
            reasons.setdefault(key(e),[]).append('boundary_inside_word')
    dropped=[e | {'abstentionReasons':reasons[key(e)]} for e in baseline['entities'] if key(e) in reasons]
    return {'entities':[e for e in baseline['entities'] if key(e) not in reasons], 'abstainedEntities':dropped, 'rawInvalidTransitions':baseline['invalidTransitions']}
