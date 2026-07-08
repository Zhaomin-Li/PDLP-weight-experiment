/*
Minimal Windows-friendly cuPDLPx MPS runner for local experiments.

This file lives outside cuPDLPx-main/src on purpose. It calls the public-ish
cuPDLPx MPS reader and C API, writes the same core output files as the upstream
CLI, and avoids changing the solver implementation.
*/

#include "cupdlpx.h"
#include "solver.h"

#ifdef __cplusplus
extern "C"
{
#endif
lp_problem_t *read_mps_file(const char *filename);
#ifdef __cplusplus
}
#endif

#include <direct.h>
#include <errno.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *termination_reason_name(termination_reason_t reason)
{
    switch (reason)
    {
        case TERMINATION_REASON_OPTIMAL:
            return "OPTIMAL";
        case TERMINATION_REASON_PRIMAL_INFEASIBLE:
            return "PRIMAL_INFEASIBLE";
        case TERMINATION_REASON_DUAL_INFEASIBLE:
            return "DUAL_INFEASIBLE";
        case TERMINATION_REASON_INFEASIBLE_OR_UNBOUNDED:
            return "INFEASIBLE_OR_UNBOUNDED";
        case TERMINATION_REASON_TIME_LIMIT:
            return "TIME_LIMIT";
        case TERMINATION_REASON_ITERATION_LIMIT:
            return "ITERATION_LIMIT";
        case TERMINATION_REASON_FEAS_POLISH_SUCCESS:
            return "FEAS_POLISH_SUCCESS";
        case TERMINATION_REASON_UNSPECIFIED:
        default:
            return "UNSPECIFIED";
    }
}

static void print_usage(const char *prog)
{
    fprintf(stderr, "Usage: %s [OPTIONS] <mps_file> <output_dir>\n", prog);
    fprintf(stderr, "Options:\n");
    fprintf(stderr, "  --time_limit <seconds>\n");
    fprintf(stderr, "  --iter_limit <iterations>\n");
    fprintf(stderr, "  --eps_opt <tolerance>\n");
    fprintf(stderr, "  --eps_feas <tolerance>\n");
    fprintf(stderr, "  --eval_freq <iterations>\n");
    fprintf(stderr, "  --opt_norm <l2|linf>\n");
    fprintf(stderr, "  --no_presolve\n");
    fprintf(stderr, "  --no_bound_obj_rescaling\n");
    fprintf(stderr, "  -q, --quiet\n");
    fprintf(stderr, "  -h, --help\n");
}

static const char *base_name(const char *path)
{
    const char *slash = strrchr(path, '/');
    const char *backslash = strrchr(path, '\\');
    const char *base = path;
    if (slash && slash + 1 > base)
        base = slash + 1;
    if (backslash && backslash + 1 > base)
        base = backslash + 1;
    return base;
}

static char *instance_name(const char *path)
{
    const char *base = base_name(path);
    size_t len = strlen(base);
    char *name = (char *)malloc(len + 1);
    if (!name)
        return NULL;
    memcpy(name, base, len + 1);

    if (len >= 7 && strcmp(name + len - 7, ".mps.gz") == 0)
        name[len - 7] = '\0';
    else if (len >= 8 && strcmp(name + len - 8, ".mps.bz2") == 0)
        name[len - 8] = '\0';
    else
    {
        char *dot = strrchr(name, '.');
        if (dot)
            *dot = '\0';
    }
    return name;
}

static char *join_output_path(const char *dir, const char *name, const char *suffix)
{
    size_t len = strlen(dir) + strlen(name) + strlen(suffix) + 2;
    char *path = (char *)malloc(len);
    if (!path)
        return NULL;
    snprintf(path, len, "%s/%s%s", dir, name, suffix);
    return path;
}

static int ensure_dir(const char *dir)
{
    if (_mkdir(dir) == 0 || errno == EEXIST)
        return 0;
    perror("Failed to create output directory");
    return 1;
}

static void save_vector(const double *data, int size, const char *dir, const char *name, const char *suffix)
{
    if (!data)
        return;

    char *path = join_output_path(dir, name, suffix);
    if (!path)
        return;

    FILE *file = fopen(path, "w");
    if (!file)
    {
        perror("Failed to open solution file");
        free(path);
        return;
    }
    for (int i = 0; i < size; ++i)
        fprintf(file, "%.17g\n", data[i]);
    fclose(file);
    free(path);
}

static void save_summary(const cupdlpx_result_t *result, const char *dir, const char *name)
{
    char *path = join_output_path(dir, name, "_summary.txt");
    if (!path)
        return;

    FILE *file = fopen(path, "w");
    if (!file)
    {
        perror("Failed to open summary file");
        free(path);
        return;
    }

    fprintf(file, "Termination Reason: %s\n", termination_reason_name(result->termination_reason));
    fprintf(file, "Precondition time (sec): %.17g\n", result->rescaling_time_sec);
    fprintf(file, "Runtime (sec): %.17g\n", result->cumulative_time_sec);
    fprintf(file, "Iterations Count: %d\n", result->total_count);
    fprintf(file, "Primal Objective Value: %.17g\n", result->primal_objective_value);
    fprintf(file, "Dual Objective Value: %.17g\n", result->dual_objective_value);
    fprintf(file, "Relative Primal Residual: %.17g\n", result->relative_primal_residual);
    fprintf(file, "Relative Dual Residual: %.17g\n", result->relative_dual_residual);
    fprintf(file, "Absolute Objective Gap: %.17g\n", result->objective_gap);
    fprintf(file, "Relative Objective Gap: %.17g\n", result->relative_objective_gap);
    fprintf(file, "Rows: %d\n", result->num_constraints);
    fprintf(file, "Columns: %d\n", result->num_variables);
    fprintf(file, "Nonzeros: %d\n", result->num_nonzeros);
    fprintf(file, "Reduced Rows: %d\n", result->num_reduced_constraints);
    fprintf(file, "Reduced Columns: %d\n", result->num_reduced_variables);
    fprintf(file, "Reduced Nonzeros: %d\n", result->num_reduced_nonzeros);
    fprintf(file, "Presolve Time (sec): %.17g\n", result->presolve_time);
    fprintf(file, "Feasibility Polishing Time (sec): %.17g\n", result->feasibility_polishing_time);
    fprintf(file, "Feasibility Polishing Iteration Count: %d\n", result->feasibility_iteration);
    fprintf(file, "Restart Count: %d\n", result->restart_count);
    fprintf(file, "Weight Update Count: %d\n", result->weight_update_count);
    fprintf(file, "Invalid Weight Reset Count: %d\n", result->invalid_weight_reset_count);
    fprintf(file, "Average Inner Iterations At Restart: %.17g\n", result->avg_inner_iterations);
    fprintf(file, "Maximum Inner Iterations At Restart: %d\n", result->max_inner_iterations);
    fprintf(file, "Clipped Event Count: %d\n", result->clipped_event_count);
    fprintf(file, "Dynamic Clip Applied Count: %d\n", result->dynamic_clip_applied_count);
    fprintf(file, "Dynamic Clip Final Radius: %.17g\n", result->dynamic_clip_final_radius);
    fprintf(file, "Dynamic Clip Min Radius: %.17g\n", result->dynamic_clip_min_radius);
    fprintf(file, "Dynamic Clip Max Radius: %.17g\n", result->dynamic_clip_max_radius);
    fprintf(file, "Dynamic Clip Expand Count: %d\n", result->dynamic_clip_expand_count);
    fprintf(file, "Dynamic Clip Shrink Count: %d\n", result->dynamic_clip_shrink_count);
    fprintf(file, "Dynamic Clip Cooldown Count: %d\n", result->dynamic_clip_cooldown_count);
    fprintf(file, "Maximum Absolute Delta Log Omega: %.17g\n", result->max_abs_delta_log_omega);
    fprintf(file, "Mean Absolute Delta Log Omega: %.17g\n", result->mean_abs_delta_log_omega);
    fprintf(file, "Excess Delta Log Omega Sum: %.17g\n", result->excess_delta_log_omega_sum);
    fprintf(file, "Delta Log Omega Sign Change Count: %d\n", result->delta_log_omega_sign_change_count);
    fprintf(file, "Delta Log Omega Sign Change Rate: %.17g\n", result->delta_log_omega_sign_change_rate);
    fprintf(file, "Initial Primal Weight: %.17g\n", result->initial_primal_weight);
    fprintf(file, "Final Primal Weight: %.17g\n", result->final_primal_weight);
    fprintf(file, "Minimum Primal Weight: %.17g\n", result->min_primal_weight);
    fprintf(file, "Maximum Primal Weight: %.17g\n", result->max_primal_weight);
    fprintf(file, "Log Primal Weight Range: %.17g\n", result->log_primal_weight_range);
    fclose(file);
    free(path);
}

static int parse_options(int argc, char **argv, pdhg_parameters_t *params, const char **mps, const char **out_dir)
{
    int i = 1;
    while (i < argc)
    {
        const char *arg = argv[i];
        if (strcmp(arg, "-h") == 0 || strcmp(arg, "--help") == 0)
            return 1;
        if (strcmp(arg, "-q") == 0 || strcmp(arg, "--quiet") == 0)
        {
            params->verbose = false;
            ++i;
        }
        else if (strcmp(arg, "--time_limit") == 0 && i + 1 < argc)
        {
            params->termination_criteria.time_sec_limit = atof(argv[i + 1]);
            i += 2;
        }
        else if (strcmp(arg, "--iter_limit") == 0 && i + 1 < argc)
        {
            params->termination_criteria.iteration_limit = atoi(argv[i + 1]);
            i += 2;
        }
        else if (strcmp(arg, "--eps_opt") == 0 && i + 1 < argc)
        {
            params->termination_criteria.eps_optimal_relative = atof(argv[i + 1]);
            i += 2;
        }
        else if (strcmp(arg, "--eps_feas") == 0 && i + 1 < argc)
        {
            params->termination_criteria.eps_feasible_relative = atof(argv[i + 1]);
            i += 2;
        }
        else if (strcmp(arg, "--eval_freq") == 0 && i + 1 < argc)
        {
            params->termination_evaluation_frequency = atoi(argv[i + 1]);
            i += 2;
        }
        else if (strcmp(arg, "--opt_norm") == 0 && i + 1 < argc)
        {
            if (strcmp(argv[i + 1], "l2") == 0)
                params->optimality_norm = NORM_TYPE_L2;
            else if (strcmp(argv[i + 1], "linf") == 0)
                params->optimality_norm = NORM_TYPE_L_INF;
            else
                return -1;
            i += 2;
        }
        else if (strcmp(arg, "--no_presolve") == 0)
        {
            params->presolve = false;
            ++i;
        }
        else if (strcmp(arg, "--no_bound_obj_rescaling") == 0)
        {
            params->bound_objective_rescaling = false;
            ++i;
        }
        else
        {
            break;
        }
    }

    if (argc - i != 2)
        return -1;
    *mps = argv[i];
    *out_dir = argv[i + 1];
    return 0;
}

int main(int argc, char **argv)
{
    pdhg_parameters_t params;
    set_default_parameters(&params);

    const char *mps = NULL;
    const char *out_dir = NULL;
    int parse_status = parse_options(argc, argv, &params, &mps, &out_dir);
    if (parse_status != 0)
    {
        print_usage(argv[0]);
        return parse_status > 0 ? 0 : 2;
    }

    if (ensure_dir(out_dir) != 0)
        return 1;

    char *name = instance_name(mps);
    if (!name)
    {
        fprintf(stderr, "Failed to allocate instance name.\n");
        return 1;
    }

    lp_problem_t *problem = read_mps_file(mps);
    if (!problem)
    {
        fprintf(stderr, "Failed to read MPS file: %s\n", mps);
        free(name);
        return 1;
    }

    if (getenv("CUPDLPX_RUNNER_DEBUG"))
    {
        volatile int *raw_eval = (volatile int *)((char *)&params + 20);
        volatile int *raw_sv = (volatile int *)((char *)&params + 24);
        fprintf(stderr,
                "[runner] params=%p problem=%p sizeof=%zu off_eval=%zu off_sv=%zu eval_freq=%d raw20=%d raw24=%d "
                "time_limit=%.17g iter_limit=%d verbose=%d presolve=%d\n",
                (void *)&params,
                (void *)problem,
                sizeof(params),
                offsetof(pdhg_parameters_t, termination_evaluation_frequency),
                offsetof(pdhg_parameters_t, sv_max_iter),
                params.termination_evaluation_frequency,
                *raw_eval,
                *raw_sv,
                params.termination_criteria.time_sec_limit,
                params.termination_criteria.iteration_limit,
                params.verbose ? 1 : 0,
                params.presolve ? 1 : 0);
    }

    cupdlpx_result_t *result = optimize(&params, problem);
    if (!result)
    {
        fprintf(stderr, "Solver failed.\n");
        lp_problem_free(problem);
        free(name);
        return 1;
    }

    save_summary(result, out_dir, name);
    save_vector(result->primal_solution, problem->num_variables, out_dir, name, "_primal_solution.txt");
    save_vector(result->dual_solution, problem->num_constraints, out_dir, name, "_dual_solution.txt");

    cupdlpx_result_free(result);
    lp_problem_free(problem);
    free(name);
    return 0;
}
