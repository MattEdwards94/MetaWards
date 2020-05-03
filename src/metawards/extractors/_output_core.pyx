#!/bin/env/python3
#cython: linetrace=False
# MUST ALWAYS DISABLE AS WAY TOO SLOW FOR ITERATE

cimport cython

from libc.stdlib cimport calloc, free
cimport openmp

from typing import Union as _Union

from .._network import Network
from .._networks import Networks
from .._population import Population
from .._infections import Infections

from .._workspace import Workspace

from ..utils._get_array_ptr cimport get_int_array_ptr, get_double_array_ptr

__all__ = ["setup_core", "output_core", "output_core_omp",
           "output_core_serial"]


cdef struct _inf_buffer:
    int count
    int *index
    int *infected


cdef _inf_buffer* _allocate_inf_buffers(int nthreads,
                                        int buffer_size=4096) nogil:
    cdef int size = buffer_size
    cdef int n = nthreads

    cdef _inf_buffer *buffers = <_inf_buffer *> calloc(n, sizeof(_inf_buffer))

    for i in range(0, n):
        buffers[i].count = 0
        buffers[i].index = <int *> calloc(size, sizeof(int))
        buffers[i].infected = <int *> calloc(size, sizeof(int))

    return buffers


cdef void _free_inf_buffers(_inf_buffer *buffers, int nthreads) nogil:
    cdef int n = nthreads

    for i in range(0, n):
        free(buffers[i].index)
        free(buffers[i].infected)

    free(buffers)


cdef void _reset_inf_buffer(_inf_buffer *buffers, int nthreads) nogil:
    cdef int n = nthreads
    cdef int i = 0

    for i in range(0, n):
        buffers[i].count = 0


cdef void _add_from_buffer(_inf_buffer *buffer, int *wards_infected) nogil:
    cdef int i = 0
    cdef int count = buffer[0].count

    for i in range(0, count):
        wards_infected[buffer[0].index[i]] += buffer[0].infected[i]

    buffer[0].count = 0


cdef inline void _add_to_buffer(_inf_buffer *buffer, int index, int value,
                                int *wards_infected,
                                openmp.omp_lock_t *lock,
                                int buffer_size=4096) nogil:
    cdef int count = buffer[0].count

    buffer[0].index[count] = index
    buffer[0].infected[count] = value
    buffer[0].count = count + 1

    if buffer[0].count >= buffer_size:
        openmp.omp_set_lock(lock)
        _add_from_buffer(buffer, wards_infected)
        openmp.omp_unset_lock(lock)
        buffer[0].count = 0


# struct to hold all of the variables that will be reduced across threads
cdef struct _red_variables:
    int n_inf_wards
    int total_new
    int inf_tot
    int pinf_tot
    int susceptibles


cdef void _reset_reduce_variables(_red_variables * variables,
                                  int nthreads) nogil:
    cdef int i = 0
    cdef int n = nthreads

    for i in range(0, n):
        variables[i].n_inf_wards = 0
        variables[i].total_new = 0
        variables[i].inf_tot = 0
        variables[i].pinf_tot = 0
        variables[i].susceptibles = 0


cdef _red_variables* _allocate_red_variables(int nthreads) nogil:
    """Allocate space for thread-local reduction variables for each
       of the 'nthreads' threads. Note that we need this as
       cython won't allow reduction in parallel blocks (only loops)
    """
    cdef int n = nthreads

    cdef _red_variables *variables = <_red_variables *> calloc(
                                                n, sizeof(_red_variables))


    _reset_reduce_variables(variables, n)

    return variables


cdef void _free_red_variables(_red_variables *variables) nogil:
    """Free the memory held by the reduction variables"""
    free(variables)


cdef void _reduce_variables(_red_variables *variables, int nthreads) nogil:
    """Reduce all of the thread-local totals in 'variables' for
       the 'nthreads' threads into the values in variables[0]
    """
    cdef int i = 0
    cdef int n = nthreads

    if n > 1:
        for i in range(1, n):
            variables[0].n_inf_wards += variables[i].n_inf_wards
            variables[0].total_new += variables[i].total_new
            variables[0].inf_tot += variables[i].inf_tot
            variables[0].pinf_tot += variables[i].pinf_tot
            variables[0].susceptibles += variables[i].susceptibles


# Global variables that are used to cache information that is needed
# from one iteration to the next - this is safe as metawards will
# only run one model run at a time per process
cdef int _buffer_nthreads = 0
cdef _inf_buffer * _total_new_inf_ward_buffers = <_inf_buffer*>0
cdef _inf_buffer * _total_inf_ward_buffers = <_inf_buffer*>0
cdef _inf_buffer * _S_buffers = <_inf_buffer*>0
cdef _inf_buffer * _E_buffers = <_inf_buffer*>0
cdef _inf_buffer * _I_buffers = <_inf_buffer*>0
cdef _inf_buffer * _R_buffers = <_inf_buffer*>0

cdef _red_variables * _redvars = <_red_variables*>0

_files = None


def setup_core(nthreads: int = 1, **kwargs):
    """This is the setup function that corresponds with
       :meth:`~metawards.extractors.output_core`.
    """
    global _buffer_nthreads

    if _buffer_nthreads != nthreads:
        global _total_new_inf_ward_buffers
        global _total_inf_ward_buffers
        global _S_buffers, _E_buffers, _I_buffers, _R_buffers
        global _redvars

        if _buffer_nthreads != 0:
            _free_red_variables(_redvars)
            _free_inf_buffers(_total_new_inf_ward_buffers, nthreads)
            _free_inf_buffers(_total_inf_ward_buffers, nthreads)
            _free_inf_buffers(_S_buffers, nthreads)
            _free_inf_buffers(_E_buffers, nthreads)
            _free_inf_buffers(_I_buffers, nthreads)
            _free_inf_buffers(_R_buffers, nthreads)

        _redvars = _allocate_red_variables(nthreads)
        _total_new_inf_ward_buffers = _allocate_inf_buffers(nthreads)
        _total_inf_ward_buffers = _allocate_inf_buffers(nthreads)
        _S_buffers = _allocate_inf_buffers(nthreads)
        _E_buffers = _allocate_inf_buffers(nthreads)
        _I_buffers = _allocate_inf_buffers(nthreads)
        _R_buffers = _allocate_inf_buffers(nthreads)
        _buffer_nthreads = nthreads


def output_core_omp(network: Network, population: Population,
                    workspace: Workspace,
                    infections: Infections,
                    nthreads: int, **kwargs):
    """This is the core output function that must be called
       every iteration as it is responsible for accumulating
       the core data each day, which is used to report a summary
       to the main output file. This is the parallel version
       of this function.

       Parameters
       ----------
       network: Network
         The network over which the outbreak is being modelled
       population: Population
         The population experiencing the outbreak
       workspace: Workspace
         A workspace that can be used to extract data
       infections: Infections
         Space to hold the nfections
       nthreads: int
         The number of threads to use to help extract the data
       kwargs
         Extra argumentst that are ignored by this function
    """
    from cython.parallel import parallel, prange

    links = network.links
    wards = network.nodes

    # set up main variables
    play_infections = infections.play
    infections = infections.work

    cdef int N_INF_CLASSES = len(infections)
    assert len(infections) == len(play_infections)

    global _total_inf_ward_buffers
    global _total_new_inf_ward_buffers
    global _redvars

    # get pointers to arrays in workspace to write data
    cdef int * inf_tot = get_int_array_ptr(workspace.inf_tot)
    cdef int * pinf_tot = get_int_array_ptr(workspace.pinf_tot)
    cdef int * total_inf_ward = get_int_array_ptr(workspace.total_inf_ward)
    cdef int * total_new_inf_ward = get_int_array_ptr(
                                                workspace.total_new_inf_ward)
    cdef int * n_inf_wards = get_int_array_ptr(workspace.n_inf_wards)
    cdef int * incidence = get_int_array_ptr(workspace.incidence)

    cdef int * S_in_wards = get_int_array_ptr(workspace.S_in_wards)
    cdef int * E_in_wards = get_int_array_ptr(workspace.E_in_wards)
    cdef int * I_in_wards = get_int_array_ptr(workspace.I_in_wards)
    cdef int * R_in_wards = get_int_array_ptr(workspace.R_in_wards)

    # get pointers to arrays from links and play to read data
    cdef int * links_ifrom = get_int_array_ptr(links.ifrom)

    cdef double * links_suscept = get_double_array_ptr(links.suscept)
    cdef double * play_suscept = get_double_array_ptr(wards.play_suscept)

    cdef int nlinks_plus_one = network.nlinks + 1
    cdef int nnodes_plus_one = network.nnodes + 1

    # Now pointers into the infections and play_infections arrays
    # so that we can read in the new infections
    cdef int * infections_i
    cdef int * play_infections_i

    # Now some loop variables used for accumulation
    cdef int total_new = 0
    cdef int susceptibles = 0

    cdef int i = 0
    cdef int j = 0

    cdef int num_threads = nthreads
    cdef int thread_id = 0
    cdef int ifrom = 0

    cdef int N_INF_CLASSES_MINUS_ONE = N_INF_CLASSES - 1

    # Finally some variables used to control parallelisation and
    # some reduction buffers
    cdef openmp.omp_lock_t lock
    openmp.omp_init_lock(&lock)

    cdef _inf_buffer * total_new_inf_ward_buffer
    cdef _inf_buffer * total_inf_ward_buffer
    cdef _inf_buffer * S_buffer
    cdef _inf_buffer * E_buffer
    cdef _inf_buffer * I_buffer
    cdef _inf_buffer * R_buffer
    cdef _red_variables * redvar

    ###
    ### Finally(!) we can now loop over the links and wards and
    ### accumulate the number of new infections in each disease class
    ###

    # reset the workspace so that we can accumulate new data for a new day
    workspace.zero_all()

    # loop over each of the disease stages
    for i in range(0, N_INF_CLASSES):
        # zero the number of infected wards, and the total number
        # of infections for this stage
        n_inf_wards[i] = 0
        inf_tot[i] = 0
        pinf_tot[i] = 0

        # similarly zero the number of infections per ward and
        # number of new infections per ward
        _reset_reduce_variables(_redvars, num_threads)
        _reset_inf_buffer(_total_inf_ward_buffers, num_threads)
        _reset_inf_buffer(_total_new_inf_ward_buffers, num_threads)

        # get pointers to the work and play infections for this disease
        # stage
        infections_i = get_int_array_ptr(infections[i])
        play_infections_i = get_int_array_ptr(play_infections[i])

        with nogil, parallel(num_threads=num_threads):
            # get the space for this thread to accumulate data.
            # All of this data will be reduced in critical sections
            thread_id = cython.parallel.threadid()
            total_inf_ward_buffer = &(_total_inf_ward_buffers[thread_id])
            total_new_inf_ward_buffer = \
                                &(_total_new_inf_ward_buffers[thread_id])
            S_buffer = &(_S_buffers[thread_id])
            E_buffer = &(_E_buffers[thread_id])
            I_buffer = &(_I_buffers[thread_id])
            R_buffer = &(_R_buffers[thread_id])
            redvar = &(_redvars[thread_id])

            # loop over all links and accumulate infections associated
            # with this link
            for j in prange(1, nlinks_plus_one, schedule="static"):
                ifrom = links_ifrom[j]

                if i == 0:
                    # susceptibles += links[j].suscept
                    redvar[0].susceptibles += <int>(links_suscept[j])
                    _add_to_buffer(S_buffer, ifrom, <int>(links_suscept[j]),
                                   &(S_in_wards[0]), &lock)

                    if infections_i[j] != 0:
                        # total_new_inf_ward[ifrom] += infections[i][j]
                        _add_to_buffer(total_new_inf_ward_buffer,
                                       ifrom, infections_i[j],
                                       &(total_new_inf_ward[0]), &lock)

                if infections_i[j] != 0:
                    # inf_tot[i] += infections[i][j]
                    redvar[0].inf_tot += infections_i[j]
                    # total_inf_ward[ifrom] += infections[i][j]
                    _add_to_buffer(total_inf_ward_buffer,
                                   ifrom, infections_i[j],
                                   &(total_inf_ward[0]), &lock)

                    if i == 0 or i == N_INF_CLASSES_MINUS_ONE:
                        _add_to_buffer(R_buffer, ifrom, infections_i[j],
                                       &(R_in_wards[0]), &lock)
                    elif i == 1:
                        _add_to_buffer(E_buffer, ifrom, infections_i[j],
                                       &(E_in_wards[0]), &lock)
                    else:
                        _add_to_buffer(I_buffer, ifrom, infections_i[j],
                                       &(I_in_wards[0]), &lock)
            # end of loop over links

            # cannot reduce in parallel, so manual reduction
            openmp.omp_set_lock(&lock)
            _add_from_buffer(total_new_inf_ward_buffer,
                             &(total_new_inf_ward[0]))
            _add_from_buffer(total_inf_ward_buffer,
                             &(total_inf_ward[0]))
            _add_from_buffer(S_buffer, &(S_in_wards[0]))
            _add_from_buffer(E_buffer, &(E_in_wards[0]))
            _add_from_buffer(I_buffer, &(I_in_wards[0]))
            _add_from_buffer(R_buffer, &(R_in_wards[0]))
            openmp.omp_unset_lock(&lock)

            # loop over all wards (nodes) and accumulate infections
            # from each ward
            for j in prange(1, nnodes_plus_one, schedule="static"):
                if i == 0:
                    # susceptibles += wards[j].suscept
                    redvar[0].susceptibles += <int>(play_suscept[j])
                    S_in_wards[j] += <int>(play_suscept[j])

                    if play_infections_i[j] > 0:
                        # total_new_inf_ward[j] += play_infections[i][j]
                        total_new_inf_ward[j] += play_infections_i[j]

                    if total_new_inf_ward[j] != 0:
                        # total_new += total_new_info_ward[j]
                        redvar[0].total_new += total_new_inf_ward[j]

                if play_infections_i[j] > 0:
                    # pinf_tot[i] += play_infections[i][j]
                    redvar[0].pinf_tot += play_infections_i[j]
                    # total_inf_ward[j] += play_infections[i][j]
                    total_inf_ward[j] += play_infections_i[j]

                    if i == 0 or i == N_INF_CLASSES_MINUS_ONE:
                        R_in_wards[j] += play_infections_i[j]
                    elif i == 1:
                        E_in_wards[j] += play_infections_i[j]
                    else:
                        I_in_wards[j] += play_infections_i[j]

                if (i < N_INF_CLASSES-1) and total_inf_ward[j] > 0:
                    # n_inf_wards[i] += 1
                    redvar[0].n_inf_wards += 1
            # end of loop over nodes
        # end of parallel

        with nogil:
            if i == 2:
                # save the sum of infections up to i <= 2. This
                # is the incidence
                for j in range(1, nnodes_plus_one):
                    incidence[j] = total_inf_ward[j]

        # can now reduce across all threads (don't need to lock as each
        # thread maintained its own running total)
        _reduce_variables(_redvars, num_threads)

        inf_tot[i] = _redvars[0].inf_tot
        pinf_tot[i] = _redvars[0].pinf_tot
        n_inf_wards[i] = _redvars[0].n_inf_wards

        # total_new += total_new[i]
        total_new += _redvars[0].total_new
        # susceptibles += susceptibles[i]
        susceptibles += _redvars[0].susceptibles

        _reset_reduce_variables(_redvars, num_threads)
    # end of loop over i

    # latent is the sum of work and play infections for stage 1
    latent = inf_tot[1] + pinf_tot[1]

    # total infections are sum of work and play for all intermediate
    # stages
    total = 0
    for i in range(2, N_INF_CLASSES-1):
        total += inf_tot[i] + pinf_tot[i]

    # recovered is the sum of work and play for the first and last stage, e.g.
    # inf_tot[0] + pinf_tot[0] + inf_tot[-1] + pinf_tot[-1]
    # (Note we don't have reverse indexing as these are plain C pointers)
    recovereds = inf_tot[0] + inf_tot[N_INF_CLASSES-1] + \
                 pinf_tot[0] + pinf_tot[N_INF_CLASSES-1]

    cdef int S = 0
    cdef int E = 0
    cdef int I = 0
    cdef int R = 0

    for j in range(1, nnodes_plus_one):
        S += S_in_wards[j]
        E += E_in_wards[j]
        I += I_in_wards[j]
        R += R_in_wards[j]

    if S != susceptibles or E != latent or I != total or R != recovereds:
        raise AssertionError(
            f"Disagreement in accumulated totals - indicates a program bug! "
            f"{S} vs {susceptibles}, {E} vs {latent}, {I} vs {total}, "
            f"{R} vs {recovereds}")

    print(f"S: {susceptibles}    ", end="")
    print(f"E: {latent}    ", end="")
    print(f"I: {total}    ", end="")
    print(f"R: {recovereds}    ", end="")
    print(f"IW: {n_inf_wards[0]}   ", end="")
    print(f"TOTAL POPULATION {susceptibles+latent+total+recovereds}")

    if population is not None:
        population.susceptibles = susceptibles
        population.total = total
        population.recovereds = recovereds
        population.latent = latent
        # save the number of wards that have at least one latent
        # infection
        population.n_inf_wards = n_inf_wards[0]

    return total + latent


def output_core_serial(network: Network, population: Population,
                       workspace: Workspace,
                       infections: Infections,
                       **kwargs):
    """This is the core output function that must be called
       every iteration as it is responsible for accumulating
       the core data each day, which is used to report a summary
       to the main output file. This is the serial version
       of this function.

       Parameters
       ----------
       network: Network
         The network over which the outbreak is being modelled
       population: Population
         The population experiencing the outbreak
       workspace: Workspace
         A workspace that can be used to extract data
       infections : Infections
         Space to hold the 'work' infections
       nthreads: int
         The number of threads to use to help extract the data
       kwargs
         Extra argumentst that are ignored by this function
    """
    links = network.links
    wards = network.nodes

    # set up main variables
    play_infections = infections.play
    infections = infections.work

    cdef int N_INF_CLASSES = len(infections)
    assert len(infections) == len(play_infections)

    # get pointers to arrays in workspace to write data
    cdef int * inf_tot = get_int_array_ptr(workspace.inf_tot)
    cdef int * pinf_tot = get_int_array_ptr(workspace.pinf_tot)
    cdef int * total_inf_ward = get_int_array_ptr(workspace.total_inf_ward)
    cdef int * total_new_inf_ward = get_int_array_ptr(
                                                workspace.total_new_inf_ward)
    cdef int * n_inf_wards = get_int_array_ptr(workspace.n_inf_wards)
    cdef int * incidence = get_int_array_ptr(workspace.incidence)

    cdef int * S_in_wards = get_int_array_ptr(workspace.S_in_wards)
    cdef int * E_in_wards = get_int_array_ptr(workspace.E_in_wards)
    cdef int * I_in_wards = get_int_array_ptr(workspace.I_in_wards)
    cdef int * R_in_wards = get_int_array_ptr(workspace.R_in_wards)

    # get pointers to arrays from links and play to read data
    cdef int * links_ifrom = get_int_array_ptr(links.ifrom)

    cdef double * links_suscept = get_double_array_ptr(links.suscept)
    cdef double * play_suscept = get_double_array_ptr(wards.play_suscept)

    cdef int nlinks_plus_one = network.nlinks + 1
    cdef int nnodes_plus_one = network.nnodes + 1

    # Now pointers into the infections and play_infections arrays
    # so that we can read in the new infections
    cdef int * infections_i
    cdef int * play_infections_i

    # Now some loop variables used for accumulation
    cdef int total_new = 0
    cdef int susceptibles = 0

    cdef int i = 0
    cdef int j = 0
    cdef int ifrom = 0

    cdef int n_inf_wards_i = 0
    cdef int total_new_i = 0
    cdef int inf_tot_i = 0
    cdef int pinf_tot_i = 0
    cdef int susceptibles_i = 0

    cdef int N_INF_CLASSES_MINUS_ONE = N_INF_CLASSES - 1

    ###
    ### Finally(!) we can now loop over the links and wards and
    ### accumulate the number of new infections in each disease class
    ###

    # reset the workspace so that we can accumulate new data for a new day
    # (make sure not to zero the subspace networks else we lose all our
    #  hard work!)
    workspace.zero_all(zero_subspaces=False)

    # loop over each of the disease stages
    for i in range(0, N_INF_CLASSES):
        # zero the number of infected wards, and the total number
        # of infections for this stage
        n_inf_wards[i] = 0
        inf_tot[i] = 0
        pinf_tot[i] = 0

        # similarly zero the number of infections per ward and
        # number of new infections per ward
        n_inf_wards_i = 0
        total_new_i = 0
        inf_tot_i = 0
        pinf_tot_i = 0
        susceptibles_i = 0

        # get pointers to the work and play infections for this disease
        # stage
        infections_i = get_int_array_ptr(infections[i])
        play_infections_i = get_int_array_ptr(play_infections[i])

        with nogil:
            # loop over all links and accumulate infections associated
            # with this link
            for j in range(1, nlinks_plus_one):
                ifrom = links_ifrom[j]

                if i == 0:
                    # susceptibles += links[j].suscept
                    susceptibles_i += <int>(links_suscept[j])
                    S_in_wards[ifrom] += <int>(links_suscept[j])

                    if infections_i[j] != 0:
                        # total_new_inf_ward[ifrom] += infections[i][j]
                        total_new_inf_ward[ifrom] += infections_i[j]

                if infections_i[j] != 0:
                    # inf_tot[i] += infections[i][j]
                    inf_tot_i += infections_i[j]
                    # total_inf_ward[ifrom] += infections[i][j]
                    total_inf_ward[ifrom] += infections_i[j]

                    if i == 0 or i == N_INF_CLASSES_MINUS_ONE:
                        R_in_wards[ifrom] += infections_i[j]
                    elif i == 1:
                        E_in_wards[ifrom] += infections_i[j]
                    else:
                        I_in_wards[ifrom] += infections_i[j]

            # end of loop over links

            # loop over all wards (nodes) and accumulate infections
            # from each ward
            for j in range(1, nnodes_plus_one):
                if i == 0:
                    # susceptibles += wards[j].suscept
                    susceptibles_i += <int>(play_suscept[j])

                    S_in_wards[j] += <int>(play_suscept[j])

                    if play_infections_i[j] > 0:
                        # total_new_inf_ward[j] += play_infections[i][j]
                        total_new_inf_ward[j] += play_infections_i[j]

                    if total_new_inf_ward[j] != 0:
                        # total_new += total_new_info_ward[j]
                        total_new_i += total_new_inf_ward[j]

                if play_infections_i[j] > 0:
                    # pinf_tot[i] += play_infections[i][j]
                    pinf_tot_i += play_infections_i[j]
                    # total_inf_ward[j] += play_infections[i][j]
                    total_inf_ward[j] += play_infections_i[j]

                    if i == 0 or i == N_INF_CLASSES_MINUS_ONE:
                        R_in_wards[j] += play_infections_i[j]
                    elif i == 1:
                        E_in_wards[j] += play_infections_i[j]
                    else:
                        I_in_wards[j] += play_infections_i[j]

                if (i < N_INF_CLASSES_MINUS_ONE) and total_inf_ward[j] > 0:
                    # n_inf_wards[i] += 1
                    n_inf_wards_i += 1
            # end of loop over nodes

            if i == 2:
                # save the sum of infections up to i <= 2. This
                # is the incidence
                for j in range(1, nnodes_plus_one):
                    incidence[j] = total_inf_ward[j]

        # end of nogil

        # can now reduce across all threads (don't need to lock as each
        # thread maintained its own running total)
        inf_tot[i] = inf_tot_i
        pinf_tot[i] = pinf_tot_i
        n_inf_wards[i] = n_inf_wards_i

        # total_new += total_new[i]
        total_new += total_new_i
        # susceptibles += susceptibles[i]
        susceptibles += susceptibles_i
    # end of loop over i

    # latent is the sum of work and play infections for stage 1
    latent = inf_tot[1] + pinf_tot[1]

    # total infections are sum of work and play for all intermediate
    # stages
    total = 0
    for i in range(2, N_INF_CLASSES-1):
        total += inf_tot[i] + pinf_tot[i]

    # recovered is the sum of work and play for the first and last stage, e.g.
    # inf_tot[0] + pinf_tot[0] + inf_tot[-1] + pinf_tot[-1]
    # (Note we don't have reverse indexing as these are plain C pointers)
    recovereds = inf_tot[0] + inf_tot[N_INF_CLASSES-1] + \
                 pinf_tot[0] + pinf_tot[N_INF_CLASSES-1]

    cdef int S = 0
    cdef int E = 0
    cdef int I = 0
    cdef int R = 0

    for j in range(1, nnodes_plus_one):
        S += S_in_wards[j]
        E += E_in_wards[j]
        I += I_in_wards[j]
        R += R_in_wards[j]

    if S != susceptibles or E != latent or I != total or R != recovereds:
        raise AssertionError(
            f"Disagreement in accumulated totals - indicates a program bug! "
            f"{S} vs {susceptibles}, {E} vs {latent}, {I} vs {total}, "
            f"{R} vs {recovereds}")

    print(f"S: {susceptibles}    ", end="")
    print(f"E: {latent}    ", end="")
    print(f"I: {total}    ", end="")
    print(f"R: {recovereds}    ", end="")
    print(f"IW: {n_inf_wards[0]}   ", end="")
    print(f"TOTAL POPULATION {susceptibles+latent+total+recovereds}")

    if population is not None:
        population.susceptibles = susceptibles
        population.total = total
        population.recovereds = recovereds
        population.latent = latent
        # save the number of wards that have at least one latent
        # infection
        population.n_inf_wards = n_inf_wards[0]

    return total + latent


def output_core(network: _Union[Network, Networks],
                population: Population,
                workspace: Workspace,
                infections: Infections,
                nthreads: int, **kwargs):
    """This is the core output function that must be called
       every iteration as it is responsible for accumulating
       the core data each day, which is used to report a summary
       to the main output file. This is the serial version
       of this function.

       Parameters
       ----------
       network: Network or Networks
         The network(s) over which the outbreak is being modelled
       population: Population
         The population experiencing the outbreak
       workspace: Workspace
         A workspace that can be used to extract data
       infections
         Space to hold the 'work' infections
       play_infections
         Space to hold the 'play' infections
       nthreads: int
         The number of threads to use to help extract the data
       kwargs
         Extra argumentst that are ignored by this function
    """

    # serial version is much faster than parallel - only worth
    # parallelising when more than 4 cores
    if nthreads <= 4:
        output_func = output_core_serial
    else:
        kwargs["nthreads"] = nthreads
        output_func = output_core_omp

    if isinstance(network, Network):
        output_func(network=network, population=population,
                    workspace=workspace, infections=infections)

    elif isinstance(network, Networks):
        if population.subpops is None:
            population.specialise(network)

        for i, subnet in enumerate(network.subnets):
            output_func(network=subnet,
                        population=population.subpops[i],
                        workspace=workspace.subspaces[i],
                        infections=infections.subinfs[i],
                        **kwargs)

        # aggregate the infection information from across
        # the different demographics
        network.aggregate(infections=infections)

        output_func(network=network.overall,
                    population=population,
                    workspace=workspace,
                    infections=infections,
                    **kwargs)
