
from typing import Callable, Optional, Tuple
import torch
import torch.nn.functional as F
from torch.distributions import Categorical
import numpy as np
from torch import nn
import math
from .pickdrop_pomo_n2s_env import Step_State

NBR_WORKER_MEAN_HEAD = 4
DROPOUT_PERCENT = 0.02

def get_initial_insert_mask(step_state:Step_State) -> torch.Tensor:
    # visited_order_map = PDP._get_visit_order_map(visit_index) 
    curr_idx = torch.arange(step_state.worker_size).view(1,step_state.worker_size).repeat(step_state.batch_pomo_size,1)
    next_idx = step_state.solution[step_state.BATCH_POMO_IDX_2D, curr_idx]
    # worker_full_map 当前定义是没有FULL的worker。 变量应该是worker_full_map --> worker_free_map
    worker_full_map = step_state.worker_selected_loc_length < step_state.max_job_in_worker_size
    worker_job_full_map = torch.ones(step_state.batch_pomo_size, step_state.worker_job_size_plus1).bool()
    worker_job_full_map = worker_job_full_map.scatter(1, curr_idx, worker_full_map)

    _step_i = 0
    # 从job的start位置开始循环，逐次找每个worker里面下一个job，把job的位置设置worker start位置上的“是否满”标志。
    while _step_i < step_state.job_size*2 and (next_idx != step_state.worker_job_size).any().item():
        _step_i +=1
        curr_idx = next_idx
        step_state.solution_job_curr_seq = step_state.solution_job_curr_seq.scatter(1, curr_idx, _step_i)
        worker_job_full_map = worker_job_full_map.scatter(1, curr_idx, worker_full_map)
        next_idx = step_state.solution[step_state.BATCH_POMO_IDX_2D, curr_idx]

    worker_full_mask = torch.logical_and( 
        worker_job_full_map.view(step_state.batch_pomo_size, step_state.worker_job_size_plus1,1).repeat(1,1, step_state.worker_job_size_plus1), 
        worker_job_full_map.view(step_state.batch_pomo_size,1, step_state.worker_job_size_plus1).repeat(1, step_state.worker_job_size_plus1,1),
    ) 
    
    pick_seq = step_state.solution_job_curr_seq[:,:step_state.worker_job_size].view(step_state.batch_pomo_size, step_state.worker_job_size, 1)
    drop_seq = step_state.solution_job_curr_seq[:,:step_state.worker_job_size].view(step_state.batch_pomo_size, 1, step_state.worker_job_size)

    visited_order_map = (pick_seq < drop_seq) # 要求pick在drop之前。

    # initial_worker_map = 1 # where start and end of work is same? or next of first == 14?

    same_worker_map = (  # 要求 选择的pick+drop的两个job插入位置的组合必须属于同一个worker
        step_state.solution_worker_idx[:,:step_state.worker_job_size].view(step_state.batch_pomo_size, step_state.worker_job_size, 1)
        == 
        step_state.solution_worker_idx[:,:step_state.worker_job_size].view(step_state.batch_pomo_size, 1, step_state.worker_job_size)
    )

    mask = torch.logical_and(
        torch.logical_and(
        visited_order_map, 
        same_worker_map), 
        worker_full_mask[:, :step_state.worker_job_size, :step_state.worker_job_size]
    )  # here true means available

    # allowed_unary_worker = (step_state.solution_job_curr_seq == 0) 
    # allowed_unary_worker = step_state.solution[:,0:step_state.worker_size] == step_state.worker_job_size
    allowed_unary_worker = torch.ones(step_state.batch_pomo_size, step_state.worker_size)
    allowed_unary_job = step_state.solution_worker_idx[:, step_state.worker_size: step_state.worker_job_size] > -1
    allowed_nodes = torch.cat([
        allowed_unary_worker, allowed_unary_job
    ], dim=-1).bool()
    allowed_nodes_free = torch.logical_and(
        allowed_nodes,
        worker_job_full_map[:, :step_state.worker_job_size]
        )
    allowed_unary = torch.diag_embed(allowed_nodes_free)
    allowed_unary_mask = (allowed_unary.bool()) # ~

    mask = torch.logical_or(mask, allowed_unary_mask)  
    return ~mask # here returning true means unavailable/*masked*



def get_swap_insert_mask(step_state:Step_State, selected_pick, selected_drop) -> torch.Tensor:

    bp_idx_t = torch.arange(step_state.batch_pomo_size)
    selected_worker = step_state.solution_worker_idx[
        bp_idx_t,
        selected_pick.view(step_state.batch_pomo_size)
    ]
    selected_worker_map = (
        step_state.solution_worker_idx[:,:step_state.worker_job_size] 
        == 
        selected_worker.view(step_state.batch_pomo_size,1)
    )
    # Int() not supported. "baddbmm_cuda" not implemented for 'Int'
    selected_worker_mask = torch.matmul(
        selected_worker_map.view(step_state.batch_pomo_size,step_state.worker_job_size,1).float(),
        selected_worker_map.view(step_state.batch_pomo_size,1,step_state.worker_job_size).float()
    ).bool()
    # Set selected removal row+col to False, which means not to be selected for insertion
    selected_worker_mask[bp_idx_t,selected_pick,:]=False
    selected_worker_mask[bp_idx_t,:,selected_pick]=False
    selected_worker_mask[bp_idx_t,selected_drop,:]=False
    selected_worker_mask[bp_idx_t,:,selected_drop]=False

    # TODO, 2023-08-27 21:52:28  I should disable pre of current selected. To avoid reinserting removal as is.
    # I will see how it affect performance 

    curr_idx = torch.arange(step_state.worker_size).view(1,step_state.worker_size).repeat(step_state.batch_pomo_size,1)
    next_idx = step_state.solution[step_state.BATCH_POMO_IDX_2D, curr_idx]#.clone()
    _step_i = 0
    while _step_i < step_state.job_size*2 and (next_idx != step_state.worker_job_size).any().item():
        _step_i +=1
        curr_idx = next_idx
        step_state.solution_job_curr_seq = step_state.solution_job_curr_seq.scatter(1, curr_idx, _step_i)
        next_idx = step_state.solution[step_state.BATCH_POMO_IDX_2D, curr_idx]#.clone()
    
    pick_seq = step_state.solution_job_curr_seq[:,:step_state.worker_job_size].view(step_state.batch_pomo_size, step_state.worker_job_size, 1)
    drop_seq = step_state.solution_job_curr_seq[:,:step_state.worker_job_size].view(step_state.batch_pomo_size, 1, step_state.worker_job_size)
    visited_order_map = (pick_seq < drop_seq) # ~

    mask = torch.logical_and( 
        selected_worker_mask,
        visited_order_map, 
    )  # here true means available
    return ~mask
 

def get_removal_node_mask(step_state:Step_State) -> torch.Tensor:

    multi_job_workers = step_state.worker_selected_loc_length > 3
    # Then overlay the slot mask if required.
    if step_state.enabled_slot_map is not None:
        multi_job_workers = torch.logical_and( 
            multi_job_workers, 
            step_state.enabled_slot_map,
        )  

    curr_idx = torch.arange(step_state.worker_size).view(1,step_state.worker_size).repeat(step_state.batch_pomo_size,1)
    next_idx = step_state.solution[step_state.BATCH_POMO_IDX_2D, curr_idx] 
    job_worker_map = torch.ones(step_state.batch_pomo_size, step_state.worker_job_size_plus1).bool()
    job_worker_map = job_worker_map.scatter(1, curr_idx, multi_job_workers)
    # worker_start_seq = curr_idx.clone()*100
    # step_state.solution[0:2,5]=14
    # curr_idx = w_initials
    # next_idx = step_state.solution[step_state.BATCH_POMO_IDX_2D, curr_idx]
    _step_i = 0
    # Only first pick job can be possible to block/mask out
    # Hence 1
    while _step_i <  step_state.job_size*2 and (next_idx != step_state.worker_job_size).any().item(): # 1: #
        _step_i +=1
        curr_idx = next_idx
        step_state.solution_job_curr_seq = step_state.solution_job_curr_seq.scatter(1, curr_idx, _step_i)
        job_worker_map = job_worker_map.scatter(1, curr_idx, multi_job_workers)
        next_idx = step_state.solution[step_state.BATCH_POMO_IDX_2D, curr_idx]
    
    return ~job_worker_map[:,step_state.worker_size :step_state.worker_size+step_state.job_size] 

class MultiHeadAttention(nn.Module):
    def __init__(
        self,
        n_heads: int,
        in_query_dim: int,
        in_key_dim: int,
        in_val_dim: Optional[int],
        out_dim: int,
    ) -> None:
        super().__init__()

        hidden_dim = out_dim // n_heads

        self.n_heads = n_heads
        self.out_dim = out_dim
        self.hidden_dim = hidden_dim
        self.in_query_dim = in_query_dim
        self.in_key_dim = in_key_dim
        self.in_val_dim = in_val_dim

        self.norm_factor = 1 / math.sqrt(hidden_dim)  # See Attention is all you need

        self.W_query = nn.Parameter(torch.Tensor(n_heads, in_query_dim, hidden_dim))
        self.W_key = nn.Parameter(torch.Tensor(n_heads, in_key_dim, hidden_dim))
        if in_val_dim is not None:  # else calculate attention score
            self.W_val = nn.Parameter(torch.Tensor(n_heads, in_val_dim, hidden_dim))
            self.W_out = nn.Parameter(torch.Tensor(n_heads, hidden_dim, out_dim))

        self.init_parameters()

    def init_parameters(self) -> None:

        for param in self.parameters():
            stdv = 1.0 / math.sqrt(param.size(-1))
            param.data.uniform_(-stdv, stdv)

    __call__: Callable[..., torch.Tensor]

    def forward(
        self,
        q: torch.Tensor,
        k: torch.Tensor,
        v: Optional[torch.Tensor] = None,
        with_norm: bool = False,
    ) -> torch.Tensor:

        if self.in_val_dim is None:  # calculate attention score
            assert v is None

        batch_size, n_query, in_que_dim = q.size()
        _, n_key, in_key_dim = k.size()

        if v is not None:
            in_val_dim = v.size(2)

        qflat = q.contiguous().view(
            -1, in_que_dim
        )  # (batch_size * n_query, in_que_dim)
        kflat = k.contiguous().view(-1, in_key_dim)  # (batch_size * n_key, in_key_dim)
        if v is not None:
            vflat = v.contiguous().view(-1, in_val_dim)

        shp_q = (self.n_heads, batch_size, n_query, self.hidden_dim)
        shp_kv = (self.n_heads, batch_size, n_key, self.hidden_dim)

        # Calculate queries, (n_heads, batch_size, n_query, hidden_dim)
        Q = torch.matmul(qflat, self.W_query).view(shp_q)
        # self.W_que: (n_heads, in_que_dim, hidden_dim)
        # Q_before_view: (n_heads, batch_size * n_query, hidden_dim)

        # Calculate keys and values (n_heads, batch_size, n_key, hidden_dim)
        K = torch.matmul(kflat, self.W_key).view(shp_kv)
        if v is not None:
            V = torch.matmul(vflat, self.W_val).view(shp_kv)

        # Calculate compatibility (n_heads, batch_size, n_query, n_key)
        compatibility = torch.matmul(Q, K.transpose(2, 3))

        if v is None and not with_norm:
            return compatibility

        compatibility = self.norm_factor * compatibility

        if v is None and with_norm:
            return compatibility

        attn = F.softmax(compatibility, dim=-1)

        heads = torch.matmul(attn, V)  # (n_heads, batch_size, n_query, hidden_dim)

        out = torch.mm(
            heads.permute(1, 2, 0, 3)  # (batch_size, n_query, n_heads, hidden_dim)
            .contiguous()
            .view(
                -1, self.n_heads * self.hidden_dim
            ),  # (batch_size * n_query, n_heads * hidden_dim)
            self.W_out.view(-1, self.out_dim),  # (n_heads * hidden_dim, out_dim)
        ).view(batch_size, n_query, self.out_dim)

        return out

class MLP(nn.Module):
    def __init__(
        self,
        input_dim: int = 128,
        feed_forward_dim: int = 64,
        embedding_dim: int = 64,
        output_dim: int = 1,
        p_dropout: float = 0.01,
    ) -> None:
        super().__init__()
        self.fc1 = nn.Linear(input_dim, feed_forward_dim)
        self.fc2 = nn.Linear(feed_forward_dim, embedding_dim)
        self.fc3 = nn.Linear(embedding_dim, output_dim)
        self.dropout = nn.Dropout(p=p_dropout)
        self.ReLU = nn.ReLU(inplace=True)

        self.init_parameters()

    def init_parameters(self) -> None:

        for param in self.parameters():
            stdv = 1.0 / math.sqrt(param.size(-1))
            param.data.uniform_(-stdv, stdv)

    __call__: Callable[..., torch.Tensor]

    def forward(self, input: torch.Tensor) -> torch.Tensor:
        result = self.ReLU(self.fc1(input))
        result = self.dropout(result)
        result = self.ReLU(self.fc2(result))
        result = self.fc3(result).squeeze(-1)
        return result




class NodePairReinsertionDecoder(nn.Module):  # (14) (15)
    def __init__(self, n_heads: int, input_dim: int) -> None:
        super().__init__()

        self.n_heads = n_heads

        self.compater_insert1 = MultiHeadAttention(
            n_heads, input_dim, input_dim, None, input_dim * n_heads
        )

        self.compater_insert2 = MultiHeadAttention(
            n_heads, input_dim, input_dim, None, input_dim * n_heads
        )
        self.worker_mean_mlp = MLP(
            input_dim = input_dim, 
            output_dim = NBR_WORKER_MEAN_HEAD*n_heads,
            p_dropout=DROPOUT_PERCENT)

        # 4 heads are from point-wise, first_before/after, second_before/after
        # 4 heads are from worker_mean_mlp
        self.agg = MLP ((4+NBR_WORKER_MEAN_HEAD) * n_heads, 32, 32, 1, p_dropout=DROPOUT_PERCENT)

    def init_parameters(self) -> None:

        for param in self.parameters():
            stdv = 1.0 / math.sqrt(param.size(-1))
            param.data.uniform_(-stdv, stdv)

    __call__: Callable[..., torch.Tensor]

    def forward(
        self,step_state, encoded_nodes, pos_pickup, pos_delivery
    ) -> torch.Tensor:
        # h_hat: torch.Tensor,
        # pos_pickup: torch.Tensor,  # (batch_size)
        # pos_delivery: torch.Tensor,  # (batch_size)
        # solution: torch.Tensor,  # (batch, graph_size+1)
        # worker_job_size == graph_size_plus1
        batch_size, worker_job_size, embedding_dim = encoded_nodes.size()
        pomo_size = step_state.reset_state.job_loc_idx.size(1)
        batch_pomo_size = step_state.batch_pomo_size

        pos_pickup = pos_pickup.view(batch_pomo_size)
        pos_delivery = pos_delivery.view(batch_pomo_size)

        h_hat = encoded_nodes.unsqueeze(1).repeat(1,pomo_size,1, 1).view(batch_pomo_size, worker_job_size, embedding_dim)

        shp = (batch_pomo_size, worker_job_size, worker_job_size, self.n_heads)
        shp_p = (batch_pomo_size, worker_job_size, 1, self.n_heads)
        shp_d = (batch_pomo_size, 1, worker_job_size, self.n_heads)
        shp_mean_1d = (batch_pomo_size, 1, worker_job_size, self.n_heads*NBR_WORKER_MEAN_HEAD)
        shp_mean_2d = (batch_pomo_size, worker_job_size, worker_job_size, self.n_heads*NBR_WORKER_MEAN_HEAD)

        b_p_arange_t = torch.arange(batch_pomo_size, device=h_hat.device)
        h_pickup = h_hat[b_p_arange_t, pos_pickup].unsqueeze(1)  # (batch_pomo_size, 1, input_dim)
        h_delivery = h_hat[b_p_arange_t, pos_delivery].unsqueeze(
            1
        )  # (batch_size, 1, input_dim)
        solution_next_i = step_state.solution[:,:worker_job_size] % worker_job_size
        h_K_neibour = h_hat.gather(
            1, solution_next_i.view(batch_pomo_size, worker_job_size, 1).expand_as(h_hat)
        )  # (batch_size, graph_size+1, input_dim)

        compatibility_pickup_pre = (
            self.compater_insert1(
                h_pickup, h_hat
            )  # (n_heads, batch_size, 1, graph_size+1)
            .permute(1, 2, 3, 0)  # (batch_size, 1, graph_size+1, n_heads)
            .view(shp_p)  # (batch_size, graph_size+1, 1, n_heads)
            .expand(shp)  # (batch_size, graph_size+1, graph_size+1, n_heads)
        )
        compatibility_pickup_post = (
            self.compater_insert2(h_pickup, h_K_neibour)
            .permute(1, 2, 3, 0)
            .view(shp_p)
            .expand(shp)
        )
        compatibility_delivery_pre = (
            self.compater_insert1(
                h_delivery, h_hat
            )  # (n_heads, batch_size, 1, graph_size+1)
            .permute(1, 2, 3, 0)  # (batch_size, 1, graph_size+1, n_heads)
            .view(shp_d)  # (batch_size, 1, graph_size+1, n_heads)
            .expand(shp)  # (batch_size, graph_size+1, graph_size+1, n_heads)
        )
        compatibility_delivery_post = (
            self.compater_insert2(h_delivery, h_K_neibour)
            .permute(1, 2, 3, 0)
            .view(shp_d)
            .expand(shp)
        )


        # encoded_nodes_mean = encoded_nodes.mean(dim=1).view(batch_size, 1, embedding_dim).repeat(1,worker_job_size,1)
        # encoded_nodes_diff = torch.cat([
        #     encoded_nodes - encoded_nodes_mean,
        #     torch.zeros(embedding_dim).view(1,1,embedding_dim).repeat(batch_size,1,1)
        # ],dim=1)

        encoded_nodes_diff_pomo_repeated = step_state.reset_state.encoded_nodes_diff.view(
            batch_size,1,worker_job_size+1,embedding_dim).repeat(1,pomo_size,1,1).view(
            batch_pomo_size,worker_job_size+1,embedding_dim
            )
        solution_worker_clone = torch.where(step_state.solution_worker_idx > -1, step_state.solution_worker_idx, step_state.worker_size)
        solution_worker_idx_padded = solution_worker_clone[:,:,None].repeat(1,1,embedding_dim)

        encoded_worker_mean = torch.zeros(batch_pomo_size, step_state.worker_size+1, embedding_dim)
        encoded_worker_mean = encoded_worker_mean.scatter_add(
            dim=1,
            index=solution_worker_idx_padded,
            src=encoded_nodes_diff_pomo_repeated)
        
        JOB_WORKER_IDX = solution_worker_clone[:,:worker_job_size,None].repeat(1,1,embedding_dim)
        job_worker_mean = torch.gather(
            input=encoded_worker_mean,
            dim = 1,
            index=JOB_WORKER_IDX,
        )
        job_worker_head = self.worker_mean_mlp(
            job_worker_mean
        ).view(shp_mean_1d).expand(shp_mean_2d)  # (batch_size, graph_size+1, graph_size+1, n_heads)

        compatibility = self.agg(
            torch.cat(
                (
                    compatibility_pickup_pre,
                    compatibility_pickup_post,
                    compatibility_delivery_pre,
                    compatibility_delivery_post,
                    job_worker_head,
                ),
                -1,
            )
        ).squeeze()
        return compatibility.view(batch_pomo_size, worker_job_size, worker_job_size)  # (batch_size, graph_size+1, graph_size+1)


class NodePairRemovalDecoder(nn.Module):  # (12) (13)
    def __init__(self, n_heads: int, input_dim: int) -> None:
        super().__init__()

        # hidden_dim = input_dim // n_heads
        hidden_dim = input_dim

        self.n_heads = n_heads
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim

        self.W_Q = nn.Parameter(torch.Tensor(n_heads, input_dim, hidden_dim))
        self.W_K = nn.Parameter(torch.Tensor(n_heads, input_dim, hidden_dim))

        self.agg = MLP(
            2 * n_heads, 32, 32, 1, 
            p_dropout=DROPOUT_PERCENT) #  + 4 是原来的removal history。暂时没有。

        self.init_parameters()

    def init_parameters(self) -> None:

        for param in self.parameters():
            stdv = 1.0 / math.sqrt(param.size(-1))
            param.data.uniform_(-stdv, stdv)

    __call__: Callable[..., torch.Tensor]

    def forward(
        self,step_state, encoded_nodes #, pos_pickup, pos_delivery
    ) -> torch.Tensor:
        _, worker_job_size, embedding_dim = encoded_nodes.size()
        pomo_size = step_state.reset_state.job_loc_idx.size(1)
        batch_pomo_size, worker_size, job_size = step_state.batch_pomo_size, step_state.worker_size, step_state.job_size
        pre = step_state.solution_pre_idx[:,: worker_job_size]
        _post_ = step_state.solution[:,: worker_job_size]#.clone()
        # Replace last (none-existing) node idx with pointing to itself.
        same_node_idx_mat = torch.arange(worker_job_size).view(1,worker_job_size).repeat(batch_pomo_size,1)
        post = torch.where(_post_==worker_job_size, same_node_idx_mat, _post_)#.clone()

        # post[post==worker_job_size] = torch.arange(worker_job_size).view(1,worker_job_size).repeat(batch_pomo_size,1)[post==worker_job_size]

        h_hat = encoded_nodes.unsqueeze(1).repeat(1,pomo_size,1, 1).view(batch_pomo_size, worker_job_size, embedding_dim)
        hflat = h_hat.contiguous().view(-1, embedding_dim)

        # Calculate queries, (n_heads, batch_size, graph_size+1, key_size)
        shp = (self.n_heads, step_state.batch_pomo_size, step_state.worker_job_size , self.hidden_dim)
        hidden_Q = torch.matmul(hflat, self.W_Q).view(shp)
        hidden_K = torch.matmul(hflat, self.W_K).view(shp)


        Q_pre = hidden_Q.gather(
            2, pre.view(1, batch_pomo_size, worker_job_size, 1
                        # ).expand_as(hidden_Q) # This one causes error: one of the variables needed for gradient computation has been modified by an inplace operation
                        ).repeat(self.n_heads, 1, 1, embedding_dim)
        )
        K_post = hidden_K.gather(
            2, post.view(1, batch_pomo_size, worker_job_size, 1
                        # ).expand_as(hidden_Q)
                        ).repeat(self.n_heads, 1, 1, embedding_dim)
        )

        compatibility = (
            (Q_pre * hidden_K).sum(-1) + (hidden_Q * K_post).sum(-1)
            - (Q_pre * K_post).sum(-1)
        ) 
        compatibility_pairing = torch.cat(
            (
                compatibility[:, :, worker_size : worker_size + job_size ],
                compatibility[:, :, worker_size + job_size : worker_job_size ],
            ),
            0,
        )  # (n_heads*2, batch_size, graph_size/2)

        compatibility_pairing_agg = self.agg( compatibility_pairing.permute(1, 2, 0)) # .squeeze()  # (batch_size, graph_size/2)

        return compatibility_pairing_agg

