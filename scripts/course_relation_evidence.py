"""A fixed lexical evidence guard: abstention never becomes a negative label."""
import hashlib
import re
import train_course_relation as relation


def sentence_spans(text):
    start = 0
    for match in re.finditer(r'(?<=[.!?])\s+(?=[A-Z])', text):
        # shortcut: conservative English abstract segmentation, not a multilingual NLP parser.
        if re.search(r'\b(?:e\.g|i\.e|et al|Fig|Dr)\.$', text[:match.start()]): continue
        yield start, match.start(); start = match.end()
    yield start, len(text)


def evidence_gate(row):
    relation.mark_pair(row)
    if hashlib.sha256(row['text'].encode('utf-8')).hexdigest() != row['textSha256']: raise ValueError('Evidence text hash mismatch')
    if row['label'] not in relation.allowed_labels(row['tail']['label']): raise ValueError('Invalid relation label')
    if row['label'] == 'NO_RELATION': return {'decision': 'model_negative_no_edge', 'evidence': None}
    text = row['text']; head, tail = row['head'], row['tail']
    start, end = min(head['start'], tail['start']), max(head['end'], tail['end'])
    window = next(((a, b) for a, b in sentence_spans(text) if a <= start and end <= b), None)
    if window is None: return {'decision': 'abstain_cross_sentence', 'evidence': None}
    a, b = window; sentence = text[a:b]
    if re.search(r'\b(?:not|never|without|no|may|might|could)\b', sentence, re.I):
        return {'decision': 'abstain_negated_or_hedged_window', 'evidence': None}
    if head['start'] < tail['start']:
        between = text[head['end']:tail['start']]
        connector = r'\b(?:for|to)\b' if row['label'] == 'USED_FOR' else r'\b(?:on|using|against)\b'
    else:
        between = text[tail['end']:head['start']]
        connector = r'\b(?:using|with|via|by)\b' if row['label'] == 'USED_FOR' else r'\b(?:using|with|by)\b'
    if not re.search(connector, between, re.I): return {'decision': 'abstain_no_directional_connector', 'evidence': None}
    if row['label'] == 'EVALUATED_ON' and not re.search(r'\b(?:evaluat\w*|test\w*|benchmark\w*|experiment\w*|performance|outperform\w*|accuracy|results?)\b', sentence, re.I):
        return {'decision': 'abstain_no_evaluation_cue', 'evidence': None}
    return {'decision': 'emit_candidate_with_local_lexical_evidence',
        'evidence': {'start': a, 'end': b, 'text': sentence, 'textSha256': row['textSha256'],
                     'offsetUnit': 'Unicode_code_points', 'semanticVerification': False}}


def apply_gate(rows):
    ledger = [row | {'evidenceGate': evidence_gate(row)} for row in rows]
    emitted = [row for row in ledger if row['evidenceGate']['decision'] == 'emit_candidate_with_local_lexical_evidence']
    return emitted, ledger
