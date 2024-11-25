
import torch
import torch.nn as nn
import torch.nn.functional as F

from dispatch.config import ADDR_DIM
from dispatch.contrib.training.n2s.nets.actor_network import Actor

class PickDropTSPN2SModel(nn.Module):

    def __init__(self, model_params):
        super().__init__()
        self.model_params = model_params

        self.encoder = PickDropTSP_Encoder(**model_params)
        self.decoder = PickDropTSP_Decoder(**model_params)
        self.encoded_nodes = None
        self.problem_size = 0
        self.actor = Actor(
            embedding_dim=model_params["embedding_dim"],
            ff_hidden_dim=model_params["ff_hidden_dim"],
            n_heads_actor=model_params["head_num"],
            n_layers=model_params["encoder_layer_num"],
            normalization="layer",
            v_range=6.0,
            seq_length=model_params["problem_size"],
        )

    def pre_forward(self, reset_state):
        pass

    def forward(self, state):
        batch_size = state.BATCH_IDX.size(0)
        pomo_size = state.BATCH_IDX.size(1)

        action, log_lh, to_critic_, entro_p = self.actor(
                x_in = state.batch_pomo_nodes,
                solution = state.solution,
                prev_action = state.prev_action,
                action_removal_record = state.action_removal_record,
                require_entropy=False,
                to_critic=False,
            )

        return action, log_lh, None
        self.encoded_nodes = self.encoder(reset_state.loc_xy)
        # self.problem_size = self.encoded_nodes.size(1)
        self.problem_size = reset_state.job_loc_idx.size(2)
        self.job_loc_idx = reset_state.job_loc_idx

        # shape: (batch, problem, EMBEDDING_DIM)
        self.decoder.set_kv(self.encoded_nodes, self.job_loc_idx)



        # Look up the loc value by selected job_seq
        current_loc = self.job_loc_idx[ 
            torch.arange(batch_size)[:,None,None],
            torch.arange(pomo_size)[None,:,None],
            state.current_node[:,:, None]
        ].squeeze(-1)
        encoded_last_node = _get_encoding(self.encoded_nodes, current_loc)

        # shape: (batch, pomo, embedding)
        new_ninf_mask = (state.next_job_mask)[:,:,0:self.problem_size] # torch.log, not need when using -inf as mask
        probs = self.decoder(encoded_last_node, ninf_mask=new_ninf_mask)
        # shape: (batch, pomo, problem)

        if self.training or self.model_params['eval_type'] == 'softmax':
            selected = probs.reshape(batch_size * pomo_size, -1).multinomial(1) \
                .squeeze(dim=1).reshape(batch_size, pomo_size)
            # shape: (batch, pomo)

            prob = probs[state.BATCH_IDX, state.POMO_IDX, selected] \
                .reshape(batch_size, pomo_size)
            # shape: (batch, pomo)

        else:
            selected = probs.argmax(dim=2)
            # shape: (batch, pomo)
            prob = None


        return selected, prob, probs


def _get_encoding(encoded_nodes, node_index_to_pick):
    # encoded_nodes.shape: (batch, problem, embedding)
    # node_index_to_pick.shape: (batch, pomo)

    batch_size = node_index_to_pick.size(0)
    pomo_size = node_index_to_pick.size(1)
    embedding_dim = encoded_nodes.size(2)

    gathering_index = node_index_to_pick[:, :, None].expand(batch_size, pomo_size, embedding_dim)
    # shape: (batch, pomo, embedding)

    picked_nodes = encoded_nodes.gather(dim=1, index=gathering_index)
    # shape: (batch, pomo, embedding)

    return picked_nodes


########################################
# ENCODER
########################################


class EncoderLayer(nn.Module):
    def __init__(self, **model_params):
        super().__init__()
        self.model_params = model_params
        embedding_dim = self.model_params['embedding_dim']
        head_num = self.model_params['head_num']
        qkv_dim = self.model_params['qkv_dim']

        self.Wq = nn.Linear(embedding_dim, head_num * qkv_dim, bias=False)
        self.Wk = nn.Linear(embedding_dim, head_num * qkv_dim, bias=False)
        self.Wv = nn.Linear(embedding_dim, head_num * qkv_dim, bias=False)
        self.multi_head_combine = nn.Linear(head_num * qkv_dim, embedding_dim)

        self.addAndNormalization1 = Add_And_Normalization_Module(**model_params)
        self.feedForward = Feed_Forward_Module(**model_params)
        self.addAndNormalization2 = Add_And_Normalization_Module(**model_params)

    def forward(self, input1):
        # input.shape: (batch, problem, EMBEDDING_DIM)
        head_num = self.model_params['head_num']

        q = reshape_by_heads(self.Wq(input1), head_num=head_num)
        k = reshape_by_heads(self.Wk(input1), head_num=head_num)
        v = reshape_by_heads(self.Wv(input1), head_num=head_num)
        # q shape: (batch, HEAD_NUM, problem, KEY_DIM)

        out_concat = multi_head_attention(q, k, v)
        # shape: (batch, problem, HEAD_NUM*KEY_DIM)

        multi_head_out = self.multi_head_combine(out_concat)
        # shape: (batch, problem, EMBEDDING_DIM)

        out1 = self.addAndNormalization1(input1, multi_head_out)
        out2 = self.feedForward(out1)
        out3 = self.addAndNormalization2(out1, out2)

        return out3
        # shape: (batch, problem, EMBEDDING_DIM)


class PickDropTSP_Encoder(nn.Module):
    def __init__(self, **model_params):
        super().__init__()
        self.model_params = model_params
        embedding_dim = self.model_params['embedding_dim']
        encoder_layer_num = self.model_params['encoder_layer_num']

        self.embedding = nn.Linear(ADDR_DIM, embedding_dim)
        # TODO 2022-12-24 05:01:15, add ReLu+Linear, and see if it improves accuracy
        self.layers = nn.ModuleList([EncoderLayer(**model_params) for _ in range(encoder_layer_num)])

    def forward(self, data):
        # data.shape: (batch, problem, 2)

        embedded_input = self.embedding(data)
        # shape: (batch, problem, embedding)

        out = embedded_input
        for layer in self.layers:
            out = layer(out)

        return out

########################################
# DECODER
########################################

class PickDropTSP_Decoder(nn.Module):
    def __init__(self, **model_params):
        super().__init__()
        self.model_params = model_params
        self.embedding_dim = embedding_dim = self.model_params['embedding_dim']
        self.head_num = head_num = self.model_params['head_num']
        self.qkv_dim = qkv_dim = self.model_params['qkv_dim']

        self.Wq_first = nn.Linear(embedding_dim, head_num * qkv_dim, bias=False)
        self.Wq_last = nn.Linear(embedding_dim, head_num * qkv_dim, bias=False)
        self.Wk = nn.Linear(embedding_dim, head_num * qkv_dim, bias=False)
        self.Wv = nn.Linear(embedding_dim, head_num * qkv_dim, bias=False)

        self.multi_head_combine = nn.Linear(head_num * qkv_dim, embedding_dim)

        self.k = None  # saved key, for multi-head attention
        self.v = None  # saved value, for multi-head_attention
        self.single_head_key = None  # saved, for single-head attention
        self.q_first = None  # saved q1, for multi-head attention

    def set_kv(self, encoded_nodes, job_loc_idx):
        # encoded_nodes.shape: (batch, problem, embedding)
        # head_num = self.model_params['head_num']
        self.batch_size, self.pomo_size, self.problem_size = \
            batch_size, pomo_size, problem_size = job_loc_idx.size()
        # -1 means pomo * problem_size
        job_loc_idx_flat = job_loc_idx.view(batch_size, -1)
        gathered_encoded_nodes = encoded_nodes[torch.arange(batch_size)[:,None], job_loc_idx_flat,:]

        self.k = reshape_by_heads(self.Wk(gathered_encoded_nodes), head_num=self.head_num)
        self.v = reshape_by_heads(self.Wv(gathered_encoded_nodes), head_num=self.head_num)
        # shape: (batch, head_num, pomo*problem, qkv_dim)

        self.single_head_key = gathered_encoded_nodes.view(
            batch_size, pomo_size, problem_size, self.embedding_dim
        ).transpose(2, 3)
        # shape: (batch, embedding, pomo*problem)

    def set_q1(self, encoded_q1):
        # encoded_q.shape: (batch, n, embedding)  # n can be 1 or pomo
        # head_num = self.model_params['head_num']

        self.q_first = reshape_by_heads(self.Wq_first(encoded_q1), head_num=self.head_num)
        # shape: (batch, head_num, n, qkv_dim)

    def forward(self, encoded_last_node, ninf_mask):
        # encoded_last_node.shape: (batch, pomo, embedding)
        # ninf_mask.shape: (batch, pomo, problem)

        # head_num = self.model_params['head_num']

        #  Multi-Head Attention
        #######################################################
        q_last = reshape_by_heads(self.Wq_last(encoded_last_node), head_num=self.head_num)
        # shape: (batch, head_num, pomo, qkv_dim)

        q =  q_last
        # shape: (batch, head_num, pomo, qkv_dim)


        out_concat = self.decoder_mha_per_pomo(
            q.view(self.batch_size, self.head_num, self.pomo_size, 1, self.qkv_dim), 
            self.k.view(self.batch_size, self.head_num, self.pomo_size, self.problem_size, self.qkv_dim), 
            self.v.view(self.batch_size, self.head_num, self.pomo_size, self.problem_size, self.qkv_dim), 
            rank3_ninf_mask=ninf_mask)
        # shape: (batch, pomo, head_num*qkv_dim)

        mh_atten_out = self.multi_head_combine(out_concat)
        # shape: (batch, pomo, embedding)

        #  Single-Head Attention, for probability calculation
        #######################################################
        score = torch.matmul(
            mh_atten_out[:,:,None,:], 
            self.single_head_key
        ).squeeze(2)
        # shape: (batch, pomo, problem)

        sqrt_embedding_dim = self.model_params['sqrt_embedding_dim']
        logit_clipping = self.model_params['logit_clipping']

        score_scaled = score / sqrt_embedding_dim
        # shape: (batch, pomo, problem)

        score_clipped = logit_clipping * torch.tanh(score_scaled)

        score_masked = score_clipped + ninf_mask

        probs = F.softmax(score_masked, dim=2)
        # shape: (batch, pomo, problem)

        return probs


    def decoder_mha_per_pomo(self, q, k, v,  rank3_ninf_mask=None):
        # q,k,v shape: (batch, head_num, pomo, problem, qkv_dim)   
        # rank3_ninf_mask.shape: (batch, pomo, problem)

        score = torch.matmul(q, k.transpose(3, 4))
        # shape: (batch, head_num, pomo, problem)

        score_scaled = score / torch.sqrt(torch.tensor(self.qkv_dim, dtype=torch.float))
        if rank3_ninf_mask is not None:
            new_mask = rank3_ninf_mask[:, None, :, None, :].expand(
                self.batch_size, self.head_num, self.pomo_size, 1, self.problem_size)
            score_scaled = score_scaled + new_mask

        # score_scaled shape: (batch, head_num, pomo, 1, problem)
        # softmax over problem
        weights = nn.Softmax(dim=4)(score_scaled)

        out = torch.matmul(weights, v).squeeze(3)
        # shape: (batch, head_num, pomo, qkv_dim)

        out_transposed = out.transpose(1, 2)
        # shape: (batch, n, head_num, qkv_dim)

        out_concat = out_transposed.reshape(
            self.batch_size, self.pomo_size, self.head_num * self.qkv_dim) 

        return out_concat

########################################
# NN SUB CLASS / FUNCTIONS
########################################

def reshape_by_heads(qkv, head_num):
    # q.shape: (batch, n, head_num*qkv_dim)   : n can be either 1 or PROBLEM_SIZE

    batch_s = qkv.size(0)
    n = qkv.size(1)

    q_reshaped = qkv.reshape(batch_s, n, head_num, -1)
    # shape: (batch, n, head_num, qkv_dim)

    q_transposed = q_reshaped.transpose(1, 2)
    # shape: (batch, head_num, n, qkv_dim)

    return q_transposed


def multi_head_attention(q, k, v,  rank3_ninf_mask=None):
    # q shape: (batch, head_num, n, qkv_dim)   : n can be either 1 or PROBLEM_SIZE
    # k,v shape: (batch, head_num, problem, qkv_dim)
    # rank2_ninf_mask.shape: (batch, problem)
    # rank3_ninf_mask.shape: (batch, pomo, problem)

    batch_s = q.size(0)
    head_num = q.size(1)
    n = q.size(2)
    qkv_dim = q.size(3)

    input_s = k.size(2)

    score = torch.matmul(q, k.transpose(2, 3))
    # shape: (batch, head_num, n, problem)

    score_scaled = score / torch.sqrt(torch.tensor(qkv_dim, dtype=torch.float))
    if rank3_ninf_mask is not None:
        score_scaled = score_scaled + rank3_ninf_mask[:, None, :, :].expand(batch_s, head_num, n, input_s)

    weights = nn.Softmax(dim=3)(score_scaled)
    # shape: (batch, head_num, n, problem)

    out = torch.matmul(weights, v)
    # shape: (batch, head_num, n, qkv_dim)

    out_transposed = out.transpose(1, 2)
    # shape: (batch, n, head_num, qkv_dim)

    out_concat = out_transposed.reshape(batch_s, n, head_num * qkv_dim)
    # shape: (batch, n, head_num*qkv_dim)

    return out_concat


class Add_And_Normalization_Module(nn.Module):
    def __init__(self, **model_params):
        super().__init__()
        embedding_dim = model_params['embedding_dim']
        self.norm = nn.InstanceNorm1d(embedding_dim, affine=True, track_running_stats=False)

    def forward(self, input1, input2):
        # input.shape: (batch, problem, embedding)

        added = input1 + input2
        # shape: (batch, problem, embedding)

        transposed = added.transpose(1, 2)
        # shape: (batch, embedding, problem)

        normalized = self.norm(transposed)
        # shape: (batch, embedding, problem)

        back_trans = normalized.transpose(1, 2)
        # shape: (batch, problem, embedding)

        return back_trans


class Feed_Forward_Module(nn.Module):
    def __init__(self, **model_params):
        super().__init__()
        embedding_dim = model_params['embedding_dim']
        ff_hidden_dim = model_params['ff_hidden_dim']

        self.W1 = nn.Linear(embedding_dim, ff_hidden_dim)
        self.W2 = nn.Linear(ff_hidden_dim, embedding_dim)

    def forward(self, input1):
        # input.shape: (batch, problem, embedding)

        return self.W2(F.relu(self.W1(input1)))
