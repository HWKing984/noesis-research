"""Ordered contextual entity-marker head; shared by fitting and safe reload."""
import torch
from transformers import BertForSequenceClassification
from transformers.modeling_outputs import SequenceClassifierOutput


class BertForEntityPairClassification(BertForSequenceClassification):
    def __init__(self, config):
        markers = getattr(config,'relation_marker_ids',[])
        if (getattr(config,'relation_representation',None) != 'entity_markers'
                or len(markers)!=5 or len(set(markers))!=5
                or any(type(i) is not int or not 0<=i<config.vocab_size for i in markers)):
            raise ValueError('Entity model requires explicit representation and distinct pinned marker IDs')
        super().__init__(config)
        self.classifier = torch.nn.Linear(2*config.hidden_size,config.num_labels)
        self.post_init()

    def forward(self, input_ids, attention_mask, token_type_ids=None):
        if input_ids.ndim!=2 or attention_mask.shape!=input_ids.shape:
            raise ValueError('Invalid entity-marker batch shape')
        masks = [input_ids.eq(i) for i in self.config.relation_marker_ids]
        head, head_close, task, dataset, tail_close = masks
        tail = task | dataset
        boundaries = (head,head_close,tail,tail_close)
        if any(not m.sum(1).eq(1).all() or not attention_mask[m].eq(1).all() for m in boundaries):
            raise ValueError('Missing, duplicate or masked entity marker')
        positions = [m.long().argmax(1) for m in boundaries]
        h, hc, t, tc = positions
        if not ((h<hc) & (t<tc) & ((hc<t) | (tc<h))).all():
            raise ValueError('Crossed or overlapping entity markers')
        hidden = self.bert(input_ids=input_ids,attention_mask=attention_mask,
                           token_type_ids=token_type_ids,return_dict=True).last_hidden_state
        rows = torch.arange(input_ids.shape[0],device=input_ids.device)
        # METHOD head then TASK/DATASET tail, never sorted by textual position.
        pair = torch.cat((hidden[rows,h],hidden[rows,t]),dim=-1)
        return SequenceClassifierOutput(logits=self.classifier(self.dropout(pair)))
