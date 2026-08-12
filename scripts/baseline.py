import sys
import pathlib
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter

sys.path.append(".")
sys.path.append("./leaps")

from prog_policies.runtime import create_task_envs
from prog_policies.search_space import get_search_space_cls
from prog_policies.search_methods import get_search_method_cls
from prog_policies.utils.experiment_events import EventReporter
from prog_policies.utils.evaluate_and_search import check_save_time, record_search
from prog_policies.utils.save_file import inside_seed_save_log_file, outside_seed_save_log_file

import time
import os

def karel_env(args):
    return create_task_envs(args)


def minigrid_env(args):
    return create_task_envs(args)

if __name__ == "__main__":

    parser = ArgumentParser(formatter_class=ArgumentDefaultsHelpFormatter)
    
    # LatentSpace, ProgrammaticSpace
    parser.add_argument("--search_space", default="ProgrammaticSpace", help="Search space class name")
    # Scheduled_HillClimbing, HillClimbing, HillClimbingLatent, CEM, CEBS
    parser.add_argument("--search_method", default="HillClimbing", help="Search method class name")
    parser.add_argument("--seed", type=int, default=0, help="Random seed for searching")
    parser.add_argument("--num_envs", type=int, default=32, help="Number of environments to search")
    # Karel: StairClimberSparse, MazeSparse, FourCorners, TopOff, Harvester, CleanHouse
    # Karel-Hard: DoorKey, OneStroke, Seeder, Snake
    # Karel-New: PathFollow, WallAvoider
    # Minigrid: LavaGap, PutNear, RedBlueDoor
    parser.add_argument("--task", default="Seeder", help="Task class name")
    parser.add_argument("--crashable", action="store_true", help="Determine whether the env will terimate upon executing invalid actions")
    parser.add_argument("--crash_penalty", type=float, default=-0.0, help="Penalty for crashing")
    parser.add_argument("--max_calls", type=int, default=1000, help="Max calls for each program")
    parser.add_argument("--sigma", type=float, default=0.1, help="Standard deviation for Gaussian noise in Latent Space")
    parser.add_argument("--k", type=int, default=1024, help="Number of neighbors to consider")
    parser.add_argument("--es", type=int, default=2, help="Number of elite candidates in CEM-based methods")
    parser.add_argument("--max_program_nums", type=int, default=1000000)
    parser.add_argument("--start_k", type=int, default=32)
    parser.add_argument("--end_k", type=int, default=2048)
    parser.add_argument("--interpolation_type", default="log")
    parser.add_argument("--scheduler_type", default="sin")
    parser.add_argument("--ratio_type", default="log")
    
    parser.add_argument("--output_dir", type=str, default=os.getenv("LLM_GS_OUTPUT_DIR", "output"))
    parser.add_argument("--output_name", type=str, default="0")
    parser.add_argument("--save_step", type=int, default=5000)
    # parser.add_argument("--output_name", type=str, default="output.json")

    args = parser.parse_args()
    args.e = args.es
    
    print(vars(args))
    event_reporter = EventReporter.from_env(args)
    event_reporter.install_exception_hook()
    event_reporter.run_started("scripts/baseline.py")
    
    output_dir = os.path.join(args.output_dir, args.task, args.output_name)
    output_dir_seed = os.path.join(output_dir, str(args.seed))
    
    if os.path.isdir(output_dir_seed):
        assert 0, "Duplicated seed."
    
    pathlib.Path(output_dir_seed).mkdir(parents=True, exist_ok=True)

    task_envs, dsl = create_task_envs(args)

    search_space_cls = get_search_space_cls(args.search_space)
    search_space = search_space_cls(dsl, args.sigma)
    search_space.set_seed(args.seed)

    search_method_cls = get_search_method_cls(args.search_method)
    if args.search_method == "Scheduled_HillClimbing":
        search_method = search_method_cls(
            args.k,
            args.e,
            args.start_k,
            args.end_k,
            args.max_program_nums,
            args.interpolation_type,
            args.scheduler_type,
            args.ratio_type,
        )
    else:
        search_method = search_method_cls(args.k, args.e)
    search_method.set_event_reporter(event_reporter)

    best_reward = -float("inf")
    best_prog = None
    
    log = {}
    log['args'] = vars(args)
    log['seed'] = args.seed

    init_time = time.time()

    previous_save_program_num = 0

    while task_envs[0].program_num < args.max_program_nums and best_reward < 1:
        previous_save_program_num = check_save_time(best_prog, best_reward, args.save_step, previous_save_program_num, search_method, task_envs, dsl, output_dir_seed, log, init_time, output_dir, args.task, args.seed)
        best_prog, best_reward, _ = record_search(best_prog, best_reward, search_method, search_space, task_envs, dsl, output_dir_seed, log, init_time, output_dir, args.task, args.seed)

        if best_reward >= 1:
            break

    search_method.record[task_envs[0].program_num] = best_reward
    search_method.program_record[task_envs[0].program_num] = dsl.parse_node_to_str(best_prog)

    inside_seed_save_log_file(log, output_dir_seed, task_envs[0].program_num, init_time, dsl.parse_node_to_str(best_prog), best_reward, search_method.record, search_method.program_record)
    outside_seed_save_log_file(output_dir, args.task, args.seed, task_envs[0].program_num, init_time, dsl.parse_node_to_str(best_prog), best_reward, search_method.record, search_method.program_record)
    event_reporter.run_finished(best_reward, task_envs[0].program_num)
