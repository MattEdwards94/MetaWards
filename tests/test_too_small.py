import os
import pytest

from metawards import Parameters, Network, Population, OutputFiles
from metawards.utils import Profiler

script_dir = os.path.dirname(__file__)
ncovparams_csv = os.path.join(script_dir, "data", "ncovparams.csv")


@pytest.mark.slow
def test_too_small(prompt=None):
    """This test repeats main_RepeatsNcov.c and validates that the
       various stages report the same results as the original C code
       for ncov
    """

    # user input parameters
    seed = 15324
    inputfile = ncovparams_csv
    line_num = 0
    UV = 0.0

    # load all of the parameters
    try:
        params = Parameters.load(parameters="march29")
    except Exception as e:
        print(f"Unable to load parameter files. Make sure that you have "
              f"cloned the MetaWardsData repository and have set the "
              f"environment variable METAWARDSDATA to point to the "
              f"local directory containing the repository, e.g. the "
              f"default is $HOME/GitHub/MetaWardsData")
        raise e

    # load the disease and starting-point input files
    params.set_disease(os.path.join(script_dir, "data", "ncov.json"))
    params.set_input_files("2011Data")
    params.add_seeds("ExtraSeedsBrighton.dat")

    # start from the parameters in the specified line number of the
    # provided input file
    variables = params.read_variables(inputfile, line_num)

    # extra parameters that are set
    params.UV = UV
    params.static_play_at_home = 0
    params.play_to_work = 0
    params.work_to_play = 0
    params.daily_imports = 0.0

    # the size of the starting population
    population = Population(initial=57104043)

    profiler = Profiler()
    profiler2 = Profiler()

    print("Building the network...")
    network = Network.build(params=params,
                            profiler=profiler,
                            max_nodes=100, max_links=100)

    print("Building it again... (should be cached)")
    network = Network.build(params=params,
                            profiler=profiler2,
                            max_nodes=100, max_links=100)

    params = params.set_variables(variables[0])
    network.update(params, profiler=None)

    print("Run the model...")
    outdir = os.path.join(script_dir, "test_integration_output")

    with OutputFiles(outdir, force_empty=True, prompt=prompt) as output_dir:
        trajectory = network.run(population=population, seed=seed,
                                 output_dir=output_dir,
                                 nsteps=30, profiler=None,
                                 nthreads=1)

    OutputFiles.remove(outdir, prompt=None)

    print("End of the run")

    print(profiler)

    print(f"Model output: {trajectory}")

    expected = Population(initial=57104043,
                          susceptibles=56081610,
                          latent=167,
                          total=60,
                          recovereds=240,
                          n_inf_wards=56,
                          day=30)

    print(f"Expect output: {expected}")

    assert trajectory[-1] == expected


if __name__ == "__main__":
    test_too_small()
