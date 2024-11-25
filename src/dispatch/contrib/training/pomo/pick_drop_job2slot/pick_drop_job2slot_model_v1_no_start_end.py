# 2022-06-24 04:37:20
# This was the version taking all points average, without start and end difference

import torch
import torch.nn as nn
import torch.nn.functional as F


class PickDropJob2SlotModel(nn.Module):

    def __init__(self, model_params):
        super().__init__()
        self.model_params = model_params
        embedding_dim = model_params["embedding_dim"]
        self.BATCH_IDX = None
        self.POMO_IDX = None

        self.encoder = Job2Slot_Encoder(**model_params)
        self.decoder = Job2Slot_Decoder(**model_params)
        self.encoded_nodes = None
        # shape: (batch, job+1, EMBEDDING_DIM)
        self.pickdrop2one_linear_1 = nn.Linear(embedding_dim*2, embedding_dim, bias=False)


    def pre_forward(self, reset_state):
        self.reset_state = reset_state

        self.BATCH_IDX = reset_state.BATCH_IDX
        self.POMO_IDX = reset_state.POMO_IDX

        self.encoded_nodes = self.encoder(
            reset_state.loc_xy
        )
        # shape: (batch, job+1, embedding)
        # self.decoder.set_kv(self.encoded_nodes)

    def forward(self, step_state):
        batch_size = self.BATCH_IDX.size(0)
        pomo_size = self.BATCH_IDX.size(1)

        encoded_workers = self._get_worker_encoding(step_state)
        encoded_current_jobs = self._get_job_encoding(step_state, batch_size, pomo_size)

        # shape: (batch, pomo, embedding)
        probs = self.decoder(encoded_current_jobs, encoded_workers, step_state)
        # shape: (batch, pomo, job+1)

        if self.training or self.model_params['eval_type'] == 'softmax':
            while True:  # to fix pytorch.multinomial bug on selecting 0 probability elements
                with torch.no_grad():
                    selected = probs.reshape(batch_size * pomo_size, -1).multinomial(1) \
                        .squeeze(dim=1).reshape(batch_size, pomo_size)
                # shape: (batch, pomo)
                prob = probs[self.BATCH_IDX, self.POMO_IDX, selected].reshape(batch_size, pomo_size)
                # shape: (batch, pomo)
                if (prob != 0).all():
                    break

        else:
            selected = probs.argmax(dim=2)
            # shape: (batch, pomo)
            prob = None  # value not needed. Can be anything.

        return selected, prob


    def _get_worker_encoding(self, step_state):
        embedding_dim = self.encoded_nodes.size(2)
        batch_size, pomo_size, worker_size,max_job_in_worker_size = step_state.worker_selected_loc_idx.size()

        job_gather_index = step_state.worker_selected_loc_idx[:,:,:,:,None].repeat(
            1,1,1,1,embedding_dim
        ) 

        job_gather_index_3d = job_gather_index.view(
            batch_size,
            pomo_size*worker_size*max_job_in_worker_size,
            embedding_dim
        )

        picked_nodes = self.encoded_nodes.gather(dim=1, index=job_gather_index_3d).view(
            batch_size,
            pomo_size, worker_size, max_job_in_worker_size,
            embedding_dim
        )
        picked_nodes_mean = picked_nodes.mean(dim = 3)
        # shape: (batch, pomo, worker, embedding)


        # TODO, 2022-02-25 18:38:47, missing len feature

        return picked_nodes_mean

    def _get_job_encoding(self, step_state, batch_size, pomo_size):
        # encoded_nodes.shape: (batch, job, embedding)
        # node_index_to_pick.shape: (batch, pomo)

        embedding_dim = self.encoded_nodes.size(2)

        pick_idx = step_state.current_job_idx 
        drop_idx = step_state.current_job_idx + self.reset_state.job_size

        #  = torch.zeros(size=( batch_size, pomo_size, 1),dtype=torch.int64) + current_job_idx
        gathering_index = self.reset_state.job_loc_idx[
            :,:,pick_idx:pick_idx+1
            ].repeat(1,1,embedding_dim)
        # gathering_index = node_index_to_pick.expand(batch_size, pomo_size, embedding_dim)
        # shape: (batch, pomo, embedding)
        picked_nodes = self.encoded_nodes.gather(dim=1, index=gathering_index)
        # shape: (batch, pomo, embedding)

        drop_gathering_index = self.reset_state.job_loc_idx[
            :,:,drop_idx:drop_idx+1
            ].repeat(1,1,embedding_dim)
        drop_picked_nodes = self.encoded_nodes.gather(dim=1, index=drop_gathering_index)

        merged_nodes = self.pickdrop2one_linear_1(
            torch.cat((picked_nodes, drop_picked_nodes), dim = 2))
        return merged_nodes


########################################
# ENCODER
########################################

class Job2Slot_Encoder(nn.Module):
    def __init__(self, **model_params):
        super().__init__()
        self.model_params = model_params
        embedding_dim = self.model_params['embedding_dim']
        encoder_layer_num = self.model_params['encoder_layer_num']

        self.embedding_node = nn.Linear(2, embedding_dim)
        self.layers = nn.ModuleList([EncoderLayer(**model_params) for _ in range(encoder_layer_num)])

    def forward(self, loc_xy):

        out = self.embedding_node(loc_xy)
        # shape: (batch, job, embedding)

        for layer in self.layers:
            out = layer(out)

        return out
        # shape: (batch, job+1, embedding)


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

        self.add_n_normalization_1 = AddAndBatchNormalization(**model_params)
        self.feed_forward = FeedForward(**model_params)
        self.add_n_normalization_2 = AddAndBatchNormalization(**model_params)

    def forward(self, input1):
        # input1.shape: (batch, job+1, embedding)
        head_num = self.model_params['head_num']

        q = reshape_by_heads(self.Wq(input1), head_num=head_num)
        k = reshape_by_heads(self.Wk(input1), head_num=head_num)
        v = reshape_by_heads(self.Wv(input1), head_num=head_num)
        # qkv shape: (batch, head_num, job, qkv_dim)

        out_concat = multi_head_attention(q, k, v)
        # shape: (batch, job, head_num*qkv_dim)

        multi_head_out = self.multi_head_combine(out_concat)
        # shape: (batch, job, embedding)

        out1 = self.add_n_normalization_1(input1, multi_head_out)
        out2 = self.feed_forward(out1)
        out3 = self.add_n_normalization_2(out1, out2)

        return out3
        # shape: (batch, job, embedding)


########################################
# DECODER
########################################

class Job2Slot_Decoder(nn.Module):
    def __init__(self, **model_params):
        super().__init__()
        self.model_params = model_params
        self.embedding_dim = embedding_dim = self.model_params['embedding_dim']
        self.head_num = head_num = self.model_params['head_num']
        self.qkv_dim = qkv_dim = self.model_params['qkv_dim']

        # self.Wq_1 = nn.Linear(embedding_dim, head_num * qkv_dim, bias=False)
        # self.Wq_2 = nn.Linear(embedding_dim, head_num * qkv_dim, bias=False)
        self.Wq_last = nn.Linear(embedding_dim+1, head_num * qkv_dim, bias=False)
        self.Wk = nn.Linear(embedding_dim, head_num * qkv_dim, bias=False)
        self.Wv = nn.Linear(embedding_dim, head_num * qkv_dim, bias=False)

        self.multi_head_combine = nn.Linear(head_num * qkv_dim, embedding_dim)

        self.k = None  # saved key, for multi-head attention
        self.v = None  # saved value, for multi-head_attention
        self.single_job_key = None  # saved, for single-head attention
        # self.q1 = None  # saved q1, for multi-head attention
        # self.q2 = None  # saved q2, for multi-head attention


    def forward(self, encoded_current_jobs, encoded_workers, step_state):
        # encoded_current_jobs.shape: (batch, pomo, embedding)
        # encoded_workers.shape: (batch_size, pomo_size, worker_size, embedding_size)
        batch_size, pomo_size, worker_size, embedding_size = encoded_workers.size()


        head_num = self.model_params['head_num'] 
        #  Multi-Head Attention
        #######################################################
        encoded_workers_3d = encoded_workers.view(batch_size, pomo_size*worker_size, embedding_size)
        k = reshape_by_heads(self.Wk(encoded_workers_3d), head_num=head_num).view(
            batch_size, self.head_num, pomo_size, worker_size, self.qkv_dim)
        v = reshape_by_heads(self.Wv(encoded_workers_3d), head_num=head_num).view(
            batch_size, self.head_num, pomo_size, worker_size, self.qkv_dim)
        q = reshape_by_heads(encoded_current_jobs, head_num=head_num)
        # shape: (batch, head_num, pomo, qkv_dim)
        # 
        out_concat = self.mha_worker(
            q, k, v,  batch_size, pomo_size, worker_size, 
            rank2_ninf_mask=step_state.ninf_mask # .view(batch_size, pomo_size*worker_size)
            )
        # shape: (batch, pomo, head_num*qkv_dim)

        mh_atten_out = self.multi_head_combine(out_concat)
        # shape: (batch, pomo, embedding)

        #  Single-Head Attention, for probability calculation
        #######################################################

        all_worker_keys = encoded_workers.transpose(2, 3)
        score = torch.matmul(mh_atten_out[:,:,None,:], all_worker_keys)
        # shape: (batch, pomo, 1, worker)
        score = score.squeeze(2)

        sqrt_embedding_dim = self.model_params['sqrt_embedding_dim']
        logit_clipping = self.model_params['logit_clipping']

        score_scaled = score / sqrt_embedding_dim
        # shape: (batch, pomo, job)

        score_clipped = logit_clipping * torch.tanh(score_scaled)

        score_masked = score_clipped + step_state.ninf_mask

        probs = F.softmax(score_masked, dim=2)
        # shape: (batch, pomo, job)

        return probs


    def mha_worker(self, q, k, v,  batch_size, pomo_size, worker_size, rank2_ninf_mask=None ):
        # q shape: (batch, head_num, pomo_size, key_dim)   : n can be either 1 or PROBLEM_SIZE
        # k,v shape: (batch, head_num, pomo_size * worker_size, key_dim)
        # rank2_ninf_mask.shape: (batch, job)
        # rank3_ninf_mask.shape: (batch, group, job)

        batch_s = q.size(0)
        head_num = q.size(1)
        n = q.size(2)
        key_dim = q.size(3)

        input_s = k.size(2)

        # shape: torch.Size([64 batch, 8 head_num, 20-pomo, 1, 6 - worker_size])
        score = torch.matmul(q[:,:,:,None,:], k.transpose(3, 4)) 
        score_scaled = score / torch.sqrt(torch.tensor(key_dim, dtype=torch.float))
        if rank2_ninf_mask is not None:
            score_scaled = score_scaled + rank2_ninf_mask[:, None, :, None, :].expand(
                batch_s, head_num, pomo_size, 1, worker_size) 

        weights = nn.Softmax(dim=4)(score_scaled)
        # shape: (batch, head_num, n, job)

        #weights.size: torch.Size([64, 8, 20, 1, 6])
        #v.size: torch.Size([64, 8, 20, 6, 16])
        out = torch.matmul(weights, v)
        # out.size(): (batch, head_num, pomo, 1, key_dim)

        out_transposed = out.squeeze(3).transpose(1, 2)
        # shape: (batch, pomo, head_num, key_dim)

        out_concat = out_transposed.reshape(batch_s, n, head_num * key_dim)
        # shape: (batch, pomo, head_num*key_dim)

        return out_concat


########################################
# NN SUB CLASS / FUNCTIONS
########################################

def reshape_by_heads(qkv, head_num):
    # q.shape: (batch, n, head_num*key_dim)   : n can be either 1 or PROBLEM_SIZE

    batch_s = qkv.size(0)
    n = qkv.size(1)

    q_reshaped = qkv.reshape(batch_s, n, head_num, -1)
    # shape: (batch, n, head_num, key_dim)

    q_transposed = q_reshaped.transpose(1, 2)
    # shape: (batch, head_num, n, key_dim)

    return q_transposed


def multi_head_attention(q, k, v, rank2_ninf_mask=None, rank3_ninf_mask=None):
    # q shape: (batch, head_num, n, key_dim)   : n can be either 1 or PROBLEM_SIZE
    # k,v shape: (batch, head_num, job, key_dim)
    # rank2_ninf_mask.shape: (batch, job)
    # rank3_ninf_mask.shape: (batch, group, job)

    batch_s = q.size(0)
    head_num = q.size(1)
    n = q.size(2)
    key_dim = q.size(3)

    input_s = k.size(2)

    score = torch.matmul(q, k.transpose(2, 3))
    # shape: (batch, head_num, n, job)

    score_scaled = score / torch.sqrt(torch.tensor(key_dim, dtype=torch.float))
    if rank2_ninf_mask is not None:
        score_scaled = score_scaled + rank2_ninf_mask[:, None, None, :].expand(batch_s, head_num, n, input_s)
    if rank3_ninf_mask is not None:
        score_scaled = score_scaled + rank3_ninf_mask[:, None, :, :].expand(batch_s, head_num, n, input_s)

    weights = nn.Softmax(dim=3)(score_scaled)
    # shape: (batch, head_num, n, job)

    out = torch.matmul(weights, v)
    # shape: (batch, head_num, n, key_dim)

    out_transposed = out.transpose(1, 2)
    # shape: (batch, n, head_num, key_dim)

    out_concat = out_transposed.reshape(batch_s, n, head_num * key_dim)
    # shape: (batch, n, head_num*key_dim)

    return out_concat


class AddAndInstanceNormalization(nn.Module):
    def __init__(self, **model_params):
        super().__init__()
        embedding_dim = model_params['embedding_dim']
        self.norm = nn.InstanceNorm1d(embedding_dim, affine=True, track_running_stats=False)

    def forward(self, input1, input2):
        # input.shape: (batch, job, embedding)

        added = input1 + input2
        # shape: (batch, job, embedding)

        transposed = added.transpose(1, 2)
        # shape: (batch, embedding, job)

        normalized = self.norm(transposed)
        # shape: (batch, embedding, job)

        back_trans = normalized.transpose(1, 2)
        # shape: (batch, job, embedding)

        return back_trans


class AddAndBatchNormalization(nn.Module):
    def __init__(self, **model_params):
        super().__init__()
        embedding_dim = model_params['embedding_dim']
        self.norm_by_EMB = nn.BatchNorm1d(embedding_dim, affine=True)
        # 'Funny' Batch_Norm, as it will normalized by EMB dim

    def forward(self, input1, input2):
        # input.shape: (batch, job, embedding)

        batch_s = input1.size(0)
        job_s = input1.size(1)
        embedding_dim = input1.size(2)

        added = input1 + input2
        normalized = self.norm_by_EMB(added.reshape(batch_s * job_s, embedding_dim))
        back_trans = normalized.reshape(batch_s, job_s, embedding_dim)

        return back_trans

class FeedForward(nn.Module):
    def __init__(self, **model_params):
        super().__init__()
        embedding_dim = model_params['embedding_dim']
        ff_hidden_dim = model_params['ff_hidden_dim']

        self.W1 = nn.Linear(embedding_dim, ff_hidden_dim)
        self.W2 = nn.Linear(ff_hidden_dim, embedding_dim)

    def forward(self, input1):
        # input.shape: (batch, job, embedding)

        return self.W2(F.relu(self.W1(input1)))