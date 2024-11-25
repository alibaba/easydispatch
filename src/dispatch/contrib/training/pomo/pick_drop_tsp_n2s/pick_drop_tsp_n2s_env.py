
from dataclasses import dataclass
import torch
from dispatch.config import ADDR_DIM, ALLOWED_MAXIMUM_MINUTES
from dispatch.contrib.training.n2s.problems.problem_pdtsp import PDTSP
@dataclass
class Reset_State:
    loc_xy: torch.Tensor
    # shape: (batch, problem, 2)
    # dist_matrix: torch.Tensor
    job_loc_idx: torch.Tensor
    allowed_maximum_minutes: int = ALLOWED_MAXIMUM_MINUTES
    allowed_minutes_importance: int = 0.1
    loc_dim: int = 3

@dataclass
class Step_State:
    BATCH_IDX: torch.Tensor
    POMO_IDX: torch.Tensor
    # shape: (batch, pomo)
    current_node: torch.Tensor = None
    # shape: (batch, pomo)
    next_job_mask: torch.Tensor = None
    # shape: (batch, pomo, node)

    batch_pomo_nodes: torch.Tensor = None
    solution: torch.Tensor = None
    prev_action: torch.Tensor = None
    prev_best_obj: torch.Tensor = None
    prev_best_solution: torch.Tensor = None
    action_removal_record: torch.Tensor = None

    reset_state: Reset_State = None
    job2slot_tsp_step = 0
    tsp_pre_forward_done = 0
    action_removal_count: int = 0

def _insert_star(
    solution: torch.Tensor,  # (batch_size, graph_size+1)
    pair_first: torch.Tensor,  # (batch_size, 1)
    first: torch.Tensor,  # (batch_size, 1)
    second: torch.Tensor,  # (batch_size, 1)
) -> torch.Tensor:
    solution = solution.clone()  # if solution=[2,0,1], means 0->2->1->0.
    graph_size_plus1 = solution.size(1)

    assert (
        (pair_first != first).all()
        and (pair_first != second).all()
        and ((pair_first + graph_size_plus1 // 2) != first).all()
        and ((pair_first + graph_size_plus1 // 2) != second).all()
    )

    # remove pair node
    pre = solution.argsort()  # pre=[1,2,0]
    pre_pair_first = pre.gather(1, pair_first)  # (batch_size, 1)
    post_pair_first = solution.gather(1, pair_first)  # (batch_size, 1)

    solution.scatter_(1, pre_pair_first, post_pair_first)  # remove pair first
    solution.scatter_(
        1, pair_first, pair_first
    )  # let: pair first -> pair first, for next line's pre correct

    pre = solution.argsort()

    pre_pair_second = pre.gather(1, pair_first + graph_size_plus1 // 2)
    post_pair_second = solution.gather(1, pair_first + graph_size_plus1 // 2)

    solution.scatter_(1, pre_pair_second, post_pair_second)  # remove pair second

    # insert pair node
    post_second = solution.gather(1, second)
    solution.scatter_(
        1, second, pair_first + graph_size_plus1 // 2
    )  # second -> pair_second
    solution.scatter_(1, pair_first + graph_size_plus1 // 2, post_second)

    post_first = solution.gather(1, first)
    solution.scatter_(1, first, pair_first)  # first -> pair_first
    solution.scatter_(1, pair_first, post_first)

    return solution


def _get_costs(
    batch_pomo_nodes: torch.Tensor, solution: torch.Tensor
) -> torch.Tensor:

    batch_size, graph_size_plus1 = solution.size()

    # calculate obj value
    d1 = batch_pomo_nodes.gather(
        1, solution.long().unsqueeze(-1).expand(batch_size, graph_size_plus1, 2)
    )
    d2 = batch_pomo_nodes
    total_travel = (d1 - d2).norm(p=2, dim=2).sum(1)  # (batch_size,)

    return total_travel

class PickDropTSPN2SEnv:
    def __init__(self, env_params,  model_params = {}):

        # Const @INIT
        ####################################
        self.env_params = env_params
        self.problem_size = env_params['problem_size']
        self.pomo_size = env_params['pomo_size']

        self.model_params = model_params
        # Const @Load_Problem
        ####################################
        self.batch_size = None
        self.BATCH_IDX = None
        self.POMO_IDX = None
        # IDX.shape: (batch, pomo)
        self.loc_xy = None
        # self.loc_size  = 1
        # shape: (batch, node, node)

        # Dynamic
        ####################################
        self.selected_count = None
        self.current_node = None
        # shape: (batch, pomo)
        self.selected_node_list = None
        # shape: (batch, pomo, 0~problem)

        self.problem = PDTSP(
            size = self.problem_size, 
            init_val_method = 'random', # random #  greedy
            check_feasible = False)

    def load_jobs(self, 
        batch_size = None, aug_factor=1, 
        loc_xy = None, 
        dist_matrix= None,
        worker_loc_idx = None, # only for compatability of job2slot training
        job_loc_idx = None,
        next_job_idx = None,
        next_job_mask = None,
        ):
        
        if loc_xy is None:
            self.batch_size = batch_size
            raise NotImplemented("You must provide loc_xy, or fail.")
        else:
            self.batch_size = batch_size = loc_xy.size(0)
            assert self.problem_size == job_loc_idx.size(2), "Wrong dimensions, for TSP with start problem, problem_size is number of nodes (1 worker + N job_pair * 2) and pomo size are pseudo-workers"
            
        self.dist_matrix = dist_matrix
        self.loc_xy = loc_xy
        
        # This is TSP. POMO replaced worker.
        # self.worker_loc_idx = worker_loc_idx
        self.job_loc_idx = job_loc_idx
        self.next_job_idx = next_job_idx
        self.next_job_mask = next_job_mask

        self.BATCH_IDX = torch.arange(self.batch_size)[
            :, None].expand(self.batch_size, self.pomo_size)
        self.POMO_IDX = torch.arange(self.pomo_size)[
            None, :].expand(self.batch_size, self.pomo_size)

        # 4-dimensional Index for jobs
        self.I4D_Batch = torch.arange(self.batch_size)[:,None,None,None]
        self.I4D_Pomo = torch.arange(self.pomo_size)[None,:,None,None]


    
    def reset(self):
        # The first node is already selected.
        self.current_node = torch.zeros((self.batch_size, self.pomo_size), dtype=torch.long)
        self.selected_count = 1
        # shape: (batch, pomo, 1)
        self.selected_node_list = self.current_node[:,:,None]
        action_removal_record = [
            torch.zeros((self.batch_size * self.pomo_size, self.problem_size // 2))
            for _ in range(self.problem_size - 1)  # N2S paper section 4.4 last sentence
        ]
        prev_action = torch.tensor([-1, -1, -1]).repeat(self.batch_size * self.pomo_size, 1) 
        batch_pomo_nodes, solution = self.get_initial_solutions()
        objective = _get_costs(batch_pomo_nodes, solution)
        
        # CREATE STEP STATE
        self.step_state = Step_State(
            BATCH_IDX=self.BATCH_IDX, 
            POMO_IDX=self.POMO_IDX,
            current_node = self.current_node,
            next_job_mask = self.next_job_mask,
            action_removal_record = action_removal_record,
            action_removal_count = 0,
            prev_action = prev_action,
            batch_pomo_nodes = batch_pomo_nodes,
            solution = solution,
            prev_best_obj = torch.stack([objective, objective]),
            prev_best_solution = torch.stack([solution, solution]),
            )
        # shape: (batch, pomo, problem)
        reward = None
        done = False

        self.step_state.reset_state = Reset_State(
            loc_xy = self.loc_xy,
            job_loc_idx = self.job_loc_idx
            )

        return self.step_state, reward, done

    def get_initial_solutions(self) -> torch.Tensor:

        batch_size = self.batch_size
        methods = "greedy"

        half_size = self.problem_size // 2

        if methods == 'random':
            candidates = torch.ones(batch_size, self.size + 1).bool()  # all Ture
            candidates[:, half_size + 1 :] = 0  # set to False
            solution = torch.zeros(batch_size, self.size + 1).long()
            selected_node = torch.zeros(batch_size, 1).long()
            candidates.scatter_(1, selected_node, 0)  # set to False

            for _ in range(self.size):
                dists: torch.Tensor = torch.ones(batch_size, self.size + 1)
                dists[~candidates] = -1e20
                dists = torch.softmax(dists, -1)
                next_selected_node = dists.multinomial(1).view(-1, 1)

                add_index = (next_selected_node <= half_size).view(-1)
                pairing = (
                    next_selected_node[next_selected_node <= half_size].view(-1, 1)
                    + half_size
                )
                candidates[add_index] = candidates[add_index].scatter_(
                    1, pairing, 1
                )

                solution.scatter_(1, selected_node, next_selected_node)
                candidates.scatter_(1, next_selected_node, 0)
                selected_node = next_selected_node
            sol = solution.expand(batch_size, self.problem_size + 1).clone()
                
        elif methods == 'greedy':
            candidates = torch.ones(batch_size*self.pomo_size, self.problem_size).bool()
            candidates[:, half_size + 1 :] = 0
            solution = torch.zeros(batch_size*self.pomo_size, self.problem_size).long()
            selected_node = torch.zeros(batch_size*self.pomo_size, 1).long()
            candidates.scatter_(1, selected_node, 0)

            all_worker_loc_indice =self.job_loc_idx.view(
                batch_size,
                self.pomo_size * self.problem_size, 
            )[:,:,None].repeat(1,1,ADDR_DIM)
            batch_nodes = self.loc_xy.gather(
                dim=1, 
                index = all_worker_loc_indice).view(
                    batch_size*self.pomo_size, self.problem_size, ADDR_DIM
                )

            for _ in range(self.problem_size - 1):

                d1 = (
                    batch_nodes
                    # .cpu()
                    .gather(
                        1,
                        selected_node.unsqueeze(-1).expand(
                            batch_size*self.pomo_size , 1, ADDR_DIM
                        ),
                    )
                )
                d2 = batch_nodes # .cpu()  # (batch_size, graph_size+1, 2)

                dists = (d1 - d2).norm(p=2, dim=2)  # (batch_size, graph_size+1)
                dists[~candidates] = 1e10
                next_selected_node = dists.min(-1)[1].view(-1, 1)

                add_index = (next_selected_node <= half_size).view(-1)
                pairing = (
                    next_selected_node[next_selected_node <= half_size].view(-1, 1)
                    + half_size
                )
                candidates[add_index] = candidates[add_index].scatter_(
                    1, pairing, 1
                )

                solution.scatter_(1, selected_node, next_selected_node)
                candidates.scatter_(1, next_selected_node, 0)
                selected_node = next_selected_node

            sol = solution # .expand(batch_size, self.problem_size + 1).clone()
        return batch_nodes, sol

    def pre_step(self):
        reward = None
        done = False
        return self.step_state, reward, done

    def step(self, step_state: Step_State, action):
        # selected.shape: (batch, pomo)
        step_state.action_removal_count +=1

        batch_size, graph_size_plus1 = step_state.solution.size()
        BATCH_IDX = torch.arange(batch_size)[:, None].expand(batch_size, graph_size_plus1)
        GRAPH_IDX = torch.arange(graph_size_plus1)[None, :].expand(batch_size, graph_size_plus1)



        pre_best_obj = step_state.prev_best_obj.view(batch_size, -1)

        cur_vec = step_state.action_removal_record.pop(0) * 0.0
        cur_vec[torch.arange(batch_size), action[:, 0]] = 1.0
        step_state.action_removal_record.append(cur_vec)

        selected_minus = action[:, 0].view(batch_size, 1)
        first = action[:, 1].view(batch_size, 1)
        second = action[:, 2].view(batch_size, 1)

        new_solution = _insert_star(step_state.solution, selected_minus + 1, first, second)
        step_state.solution = new_solution

        new_objective = _get_costs(step_state.batch_pomo_nodes, step_state.solution)
        best_n_new_objs = torch.cat((new_objective[:, None], pre_best_obj[:, -1, None]), -1)
        now_best_objective, min_indices = torch.min(
            best_n_new_objs, -1 # 
        )

        best_n_new_solutions = torch.cat([
                new_solution[:,:,None], 
                step_state.prev_best_solution[-1, :, :][:,:,None], 
            ], dim=-1)
        MIN_IDX = min_indices[:, None].repeat(1, graph_size_plus1)
        now_best_solution = best_n_new_solutions[BATCH_IDX, GRAPH_IDX, MIN_IDX ]

        step_state.prev_best_obj = torch.cat((
            new_objective[:, None], 
            now_best_objective[:, None]), -1)
        step_state.prev_best_solution = torch.stack([new_solution, now_best_solution, ])


        # reward = pre_best_obj[:, -1] - now_best_objective  # (batch_size,)



        # returning values
        done = (step_state.action_removal_count >= self.problem_size // 2)
        if done:
            if self.env_params["serving_only_n_no_reward"]:
                reward = 0
            else:
                # reward = -self._get_travel_distance_by_euclidean()  # note the minus sign!
                reward = 0 - new_objective # new_objective # now_best_objective
            
        else:
            reward = 0
        self.step_state = step_state
        return step_state, reward, done

    def _get_travel_distance_by_euclidean(self):
        gathering_index = self.selected_node_list.unsqueeze(3).expand(self.batch_size, -1, self.problem_size, 2)
        # shape: (batch, pomo, problem, 2)
        seq_expanded = self.loc_xy[:, None, :, :].expand(self.batch_size, self.pomo_size, self.problem_size, 2)

        ordered_seq = seq_expanded.gather(dim=2, index=gathering_index)
        # shape: (batch, pomo, problem, 2)

        rolled_seq = ordered_seq.roll(dims=2, shifts=-1)
        segment_lengths = ((ordered_seq-rolled_seq)**2).sum(3).sqrt()
        # shape: (batch, pomo, problem)

        travel_distances = segment_lengths.sum(2)
        # shape: (batch, pomo)
        return travel_distances # , segment_lengths


    def _get_travel_distance_by_matrix(self): 
        loc_size = self.loc_xy.size(1)
        self.selected_loc_list = self.job_loc_idx[ 
            torch.arange(self.batch_size)[:,None,None],
            torch.arange(self.pomo_size)[None,:,None],
            self.selected_node_list
        ]

        ordered_nodes = self.selected_loc_list.view(
            self.batch_size, self.pomo_size,self.problem_size,
        ) 
        rolled_nodes = ordered_nodes.roll(dims=2, shifts=-1)
        # To remove last travel back to depot/starting point
        rolled_nodes[:,:,-1] = ordered_nodes[:,:,-1]


        linear_index = ordered_nodes.view(
            self.batch_size, self.pomo_size*(self.problem_size) 
        ) * loc_size + rolled_nodes.view(
            self.batch_size, self.pomo_size*(self.problem_size) 
        )

        # This solution has stride problem. maybe shape()?
        # linear_index = ordered_nodes[:,:,0:self.problem_size-1].view(
        #     self.batch_size, self.pomo_size*(self.problem_size-1) 
        # ) * self.problem_size + rolled_nodes[:,:,0:self.problem_size-1].view(
        #     self.batch_size, self.pomo_size*(self.problem_size-1) 
        # )

        dist = self.dist_matrix.view(self.batch_size, loc_size**2)[
            torch.arange(self.batch_size)[:, None,],
            linear_index
        ].view(
            self.batch_size,self.pomo_size,self.problem_size
        )

        travel_distances = dist.sum(2)
        if ADDR_DIM <= 2:
            return travel_distances
        else:
            # Now I calculate the time limit penalty (cumsum of minutes as arrival)
            dist_cumsum = torch.cumsum(dist, dim=2)
            dist_cumsum = dist_cumsum.roll(dims=2, shifts=1)
            dist_cumsum[:,:,0] = 0
            allowed_cumsum = self.loc_xy[:,:,2] [
                torch.arange(self.batch_size)[:,None,None],
                self.selected_loc_list
            ] * self.step_state.reset_state.allowed_maximum_minutes

            missed_minutes = dist_cumsum - allowed_cumsum
            missed_minutes[missed_minutes < 0] = 0
            total_missed_minutes = missed_minutes.sum(2)*self.step_state.reset_state.allowed_minutes_importance


            return travel_distances + total_missed_minutes

