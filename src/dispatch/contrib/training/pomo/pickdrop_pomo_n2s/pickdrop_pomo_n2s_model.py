# 2022-06-24 04:37:20
# This is a new V2 version which use start and end position together to run transformer.

import torch
import torch.nn as nn
import torch.nn.functional as F

from dispatch.contrib.training.pomo.pick_drop_tsp_with_start.pick_drop_tsp_with_start_model import PickDropTSP_Decoder #, PickDropTSP_Encoder

from dispatch.config import ADDR_DIM
from .pickdrop_pomo_n2s_model_nets import NodePairRemovalDecoder, NodePairReinsertionDecoder, get_initial_insert_mask, get_removal_node_mask, get_swap_insert_mask


class PickDropPomoN2SModel(nn.Module):

    def __init__(self, model_params):
        super().__init__()
        self.model_params = model_params
        self.embedding_dim = model_params["embedding_dim"]
        self.BATCH_IDX = None
        self.POMO_IDX = None
        self.v_range = model_params["v_range"]
        self.problem_size = model_params["max_job_in_worker_size"]

        self.encoder = Job2Slot_Encoder(**model_params)
        # self.decoder = Job2Slot_Decoder(**model_params)

        # self.tsp_encoder = PickDropTSP_Encoder(**model_params)
        # self.tsp_decoder = PickDropTSP_Decoder(**model_params)
        
        self.encoded_nodes = None

        n_heads = model_params["head_num"]
        self.embedding_dim = model_params["embedding_dim"]

        self.compater_removal = NodePairRemovalDecoder(n_heads, self.embedding_dim)
        self.compater_reinsertion = NodePairReinsertionDecoder(
            n_heads = n_heads, 
            input_dim = self.embedding_dim)


    def pre_forward(self, reset_state):
        batch_size, worker_job_size, _ = reset_state.loc_xy.size()
        self.encoded_nodes = self.encoder(
            reset_state.loc_xy
        )
        self.reset_state = reset_state
        self.BATCH_IDX = reset_state.BATCH_IDX
        self.POMO_IDX = reset_state.POMO_IDX
        self.TSP_POMO_IDX = reset_state.TSP_POMO_IDX

        reset_state.encoded_nodes_mean = self.encoded_nodes.mean(dim=1)
        reset_state.encoded_nodes_diff = torch.cat([
            self.encoded_nodes - reset_state.encoded_nodes_mean.view(batch_size, 1, self.embedding_dim).repeat(1,worker_job_size,1),
            torch.zeros(self.embedding_dim).view(1,1,self.embedding_dim).repeat(batch_size,1,1)
        ],dim=1)


        self.batch_size, self.pomo_size, self.worker_size = reset_state.worker_loc_idx.size()
        self.tsp_pomo_size = self.pomo_size * self.worker_size


    def pre_tsp_forward(self, step_state):
        batch, ps, ws, problem_size = step_state.worker_selected_loc_idx.size()

        self.tsp_decoder.set_kv(
            self.encoded_nodes, 
            step_state.worker_selected_loc_idx.view(
                batch, ps*ws, problem_size
            ),
        )

        # worker_xy = reset_state.loc_xy[:,0:reset_state.worker_size,:]
        # worker_xy_2 = torch.cat((worker_xy,worker_xy),dim=2)

        # pick_xy = reset_state.loc_xy[:,reset_state.worker_size:reset_state.worker_size+reset_state.job_size,:]
        # drop_xy = reset_state.loc_xy[:,reset_state.worker_size+reset_state.job_size:reset_state.worker_size+reset_state.job_size+reset_state.job_size,:]
        # job_xy_2 = torch.cat((pick_xy,drop_xy),dim=2)

        # shape: (batch, job+1, embedding)
        # self.decoder.set_kv(self.encoded_nodes)

    def forward(self, step_state):
        if self.encoded_nodes is None:
            raise ValueError("not pre_forward-ed")
            self.pre_forward(step_state.reset_state)
        if step_state.job2slot_n2s_step == 0:
            return self.forward_job2slot(step_state)
        else:
            return self.forward_swap(step_state)


    def forward_job2slot(self, step_state): 
        mask_table = get_initial_insert_mask(step_state) 

        job_idx = step_state.job2slot_current_job_i # + step_state.reset_state.worker_size
        pos_pickup = step_state.reset_state.job_loc_idx[:,:, job_idx:job_idx + 1,0]# .repeat(1, embedding_dim)
        pos_delivery = step_state.reset_state.job_loc_idx[:,:, job_idx:job_idx + 1,1]# .view(batch_pomo_size)# .repeat(1, embedding_dim)

        action_reinsertion_table_1 = self.compater_reinsertion(
            step_state = step_state, 
            encoded_nodes = self.encoded_nodes,
            pos_pickup = pos_pickup,
            pos_delivery = pos_delivery
            )
        action_reinsertion_table = (
                torch.tanh(action_reinsertion_table_1)
                * self.v_range
            )
        action_reinsertion_table[mask_table] = -1e25
        del mask_table
        action_reinsertion_table = action_reinsertion_table.view(step_state.batch_pomo_size, -1)
        # log_ll_reinsertion = F.log_softmax(action_reinsertion_table, dim=-1) 
        probs_reinsertion = F.softmax(action_reinsertion_table, dim=-1)
        pair_index = probs_reinsertion.multinomial(1)
        BATCH_POMO_IDX_2D = torch.arange(step_state.batch_pomo_size)[:,None]
        prob = probs_reinsertion[BATCH_POMO_IDX_2D, pair_index] # .reshape(self.batch_size, self.pomo_size)

        p_selected = pair_index // step_state.worker_job_size
        d_selected = pair_index % step_state.worker_job_size
        action = torch.cat(
            [torch.ones(step_state.batch_pomo_size, 1), 
             pos_pickup.view(step_state.batch_pomo_size, 1), 
             pos_delivery.view(step_state.batch_pomo_size, 1),
             p_selected, 
             d_selected
             ], 
            dim=-1
        ).long()

        # if self.training and self.model_params['eval_type'] == 'softmax': # changed from or to add 2023-03-25 07:57:55
        ###########
        # else:
        #     selected = probs.argmax(dim=2)
        #     # shape: (batch, pomo)
        #     prob = None  # value not needed. Can be anything.

        return action, prob, probs_reinsertion



    def forward_swap(self, step_state):

        # 1 - Find removal candidates
        ####################################
        removal_mask = get_removal_node_mask(step_state) 
        # linked_pick_mask = (step_state.solution==14)
        # 还有只有一个job的
        # 还有上一次的选择removal
        action_removal_table_1 = self.compater_removal(            
                                step_state = step_state, 
                                encoded_nodes = self.encoded_nodes,
                            )
        action_removal_table = torch.tanh(
                            action_removal_table_1 # .squeeze()
                        ) * self.v_range 

        action_removal_table[removal_mask] = -1e25
        log_ll_removal = F.log_softmax(action_removal_table, dim=-1) # log-likelihood
        probs_removal = F.softmax(action_removal_table, dim=-1)
        action_removal_pickup = probs_removal.multinomial(1)
        selected_log_ll_removal = log_ll_removal.gather(1, action_removal_pickup) 

        action_removal_pickup = action_removal_pickup + step_state.worker_size
        action_removal_delivery = action_removal_pickup + step_state.job_size

        swap_insert_mask = get_swap_insert_mask(
            step_state = step_state, 
            selected_pick = action_removal_pickup.view(step_state.batch_pomo_size),
            selected_drop = action_removal_delivery.view(step_state.batch_pomo_size),
        ) 

        action_reinsertion_table_1 = self.compater_reinsertion(
            step_state = step_state, 
            encoded_nodes = self.encoded_nodes,
            pos_pickup = action_removal_pickup,
            pos_delivery = action_removal_delivery,

            )
        action_reinsertion_table = (
                torch.tanh(action_reinsertion_table_1)
                * self.v_range
            )
        
        action_reinsertion_table[swap_insert_mask] = -1e25
        del swap_insert_mask, removal_mask

        action_reinsertion_table = action_reinsertion_table.view(step_state.batch_pomo_size, -1)
        probs_reinsertion = F.softmax(action_reinsertion_table, dim=-1)
        pair_index = probs_reinsertion.multinomial(1)
        log_ll_reinsertion = F.log_softmax(action_reinsertion_table, dim=-1).gather(1, pair_index) 

        # BATCH_POMO_IDX_2D = torch.arange(step_state.batch_pomo_size)[:,None]
        # prob = probs_reinsertion[BATCH_POMO_IDX_2D, pair_index] # .reshape(self.batch_size, self.pomo_size)
        prob = (selected_log_ll_removal + log_ll_reinsertion).exp()

        p_selected = pair_index // step_state.worker_job_size
        d_selected = pair_index % step_state.worker_job_size
        action = torch.cat(
            [-torch.ones(step_state.batch_pomo_size, 1), 
             action_removal_pickup.view(step_state.batch_pomo_size, 1), 
             action_removal_delivery.view(step_state.batch_pomo_size, 1),
             p_selected, 
             d_selected
             ], 
            dim=-1
        ).long()
 
        return action, prob, probs_reinsertion


    def _get_job_encoding(self, step_state, batch_size, pomo_size):
        # encoded_nodes.shape: (batch, job, embedding)
        # node_index_to_pick.shape: (batch, pomo)

        # embedding_dim = self.encoded_nodes.size(2)

        job_idx = step_state.job2slot_current_job_i # + step_state.reset_state.worker_size
        pick_gathering_idx = self.reset_state.job_loc_idx[:,:, job_idx:job_idx + 1,0].repeat(1,1,self.embedding_dim)
        drop_gathering_idx = self.reset_state.job_loc_idx[:,:, job_idx:job_idx + 1,1].repeat(1,1,self.embedding_dim)

        #  = torch.zeros(size=( batch_size, pomo_size, 1),dtype=torch.int64) + job2slot_current_job_i
        gathering_index = self.reset_state.job_loc_idx[
            :,:,job_idx:job_idx+1,0
            ].repeat(1,1,self.embedding_dim)
        # gathering_index = node_index_to_pick.expand(batch_size, pomo_size, embedding_dim)
        # shape: (batch, pomo, embedding)
        picked_pick_nodes = self.encoded_nodes.gather(dim=1, index=pick_gathering_idx)
        picked_drop_nodes = self.encoded_nodes.gather(dim=1, index=drop_gathering_idx)
        # shape: (batch, pomo, embedding)
        picked_nodes_mean = (picked_pick_nodes + picked_drop_nodes) / 2

        # drop_gathering_index = self.reset_state.job_loc_idx[
        #     :,:,job_idx:job_idx+1,1
        #     ].repeat(1,1,embedding_dim)
        # drop_nodes = self.encoded_nodes.gather(dim=1, index=drop_gathering_index)
 
        return picked_nodes_mean


########################################
# ENCODER
########################################

class Job2Slot_Encoder(nn.Module):
    def __init__(self, **model_params):
        super().__init__()
        self.model_params = model_params
        embedding_dim = self.model_params['embedding_dim']
        encoder_layer_num = self.model_params['encoder_layer_num']

        self.embedding_node = nn.Linear(ADDR_DIM, embedding_dim)
        self.layers = nn.ModuleList([EncoderLayer(**model_params) for _ in range(encoder_layer_num)])

        # 2023-09-30 04:05:43, I was trying torch transformer, it did not worker .

        #  ###### self.norm = nn.InstanceNorm1d(embedding_dim, affine=True, track_running_stats=False)
        # self.norm = nn.BatchNorm1d(embedding_dim, affine=True)
        # torch_encoder_layer = nn.TransformerEncoderLayer(
        #     d_model=self.model_params['embedding_dim'], 
        #     nhead=self.model_params['head_num'])
        # self.torch_transformer_encoder = nn.TransformerEncoder(
        #     torch_encoder_layer, 
        #     norm = self.norm,
        #     num_layers=self.model_params['encoder_layer_num'])


    def forward(self, loc_xy):

        embedded = self.embedding_node(loc_xy)
        # shape: (batch, job, embedding)
        out = embedded
        for layer in self.layers:
            out = layer(out)
        return out 

        # # 2023-09-30 04:05:43, I was trying torch transformer, it did not worker .
        # (batch_s, job_s, embedding_s) = embedded.size()
        # out = self.torch_transformer_encoder(embedded.view(batch_s * job_s, embedding_s))
        # return out.view(batch_s, job_s, embedding_s)



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
        # 2023-09-30 13:39:15, 跳过两个add_n_normalization 就能用multi GPU了。
        # 但是效果很不好。
        # 2023-10-21 04:51:37 跳过Norm导致std 降低，后来不能训练了。
        # return self.feed_forward(multi_head_out)

        # It is related to this issue: https://github.com/pytorch/pytorch/issues/66504
        # BatchNorm runtimeError: one of the variables needed for gradient computation has been modified by an inplace operation #66504

        out1 = self.add_n_normalization_1(input1, multi_head_out)
        # return out1
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
        if step_state.ninf_mask is None:
            score_masked = score_clipped
        else:
            score_masked = score_clipped + step_state.ninf_mask

        probs = F.softmax(score_masked, dim=2)
        # shape: (batch, pomo, job)

        return probs


    def mha_worker(self, q, k, v,  batch_size, pomo_size, worker_size, rank2_ninf_mask=True):
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


# class AddAndInstanceNormalization(nn.Module):
#     def __init__(self, **model_params):
#         super().__init__()
#         embedding_dim = model_params['embedding_dim']
#         self.norm = nn.InstanceNorm1d(embedding_dim, affine=True, track_running_stats=False)

#     def forward(self, input1, input2):
#         # input.shape: (batch, job, embedding)

#         added = input1 + input2
#         # shape: (batch, job, embedding)

#         transposed = added.transpose(1, 2)
#         # shape: (batch, embedding, job)

#         normalized = self.norm(transposed)
#         # shape: (batch, embedding, job)

#         back_trans = normalized.transpose(1, 2)
#         # shape: (batch, job, embedding)

#         return back_trans


class AddAndBatchNormalization_SyncBatchNorm(nn.Module):
    def __init__(self, **model_params):
        super().__init__()
        embedding_dim = model_params['embedding_dim']
        # self.norm_net = nn.BatchNorm1d(embedding_dim, affine=True) 
        self.norm_net = nn.SyncBatchNorm(embedding_dim) 


    def forward(self, input1, input2):
        # input.shape: (batch, job, embedding)

        # batch_s = input1.size(0)
        # job_s = input1.size(1)
        # embedding_dim = input1.size(2)

        added = (input1 + input2 ).transpose(1,2)# .clone()
        normalized = self.norm_net(added) 
        back_trans = normalized.transpose(1,2)

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