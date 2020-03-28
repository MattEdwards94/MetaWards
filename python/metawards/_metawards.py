
import math
from array import array

from ._parameters import Parameters
from ._network import Network
from ._node import Node
from ._nodes import Nodes
from ._tolink import ToLink
from ._tolinks import ToLinks


__all__ = ["read_done_file",
           "build_wards_network",
           "build_wards_network_distance",
           "initialise_infections",
           "initialise_play_infections",
           "get_min_max_distances",
           "reset_everything",
           "rescale_play_matrix",
           "move_population_from_play_to_work"]


def move_population_from_play_to_work(network: Network, params: Parameters,
                                      rng):
    """And Vice Versa From Work to Play
       The relevant parameters are par->PlayToWork
                                   and par->WorkToPlay

       When both are 0, don't do anything;
       When PlayToWork > 0 move par->PlayToWork proportion from Play to Work.
       When WorkToPlay > 0 move par->WorkToPlay proportion from Work to Play.
    """

    countrem = 0.0
    check = 0.0     # don't use check and doesn't use the random generator?

    links = network.to_links   # workers, regular movements
    wards = network.nodes
    play = network.play        # links of players

    if params.work_to_play > 0.0:
        for i in range(1, network.nlinks+1):
            to_move = math.ceil(links[i].suscept * params.work_to_play)

            if to_move > links[i].suscept:
                print(f"to_move > links[{i}].suscept")

            links[i].suscept -= to_move
            wards[links[i].ifrom].play_suscept += to_move

    if params.play_to_work > 0.0:
        for i in range(1, network.plinks+1):
            temp = params.play_to_work * (play[i].weight *
                                          wards[play[i].ifrom].save_play_suscept)

            to_move = math.floor(temp)
            p = temp - to_move

            countrem += p

            if countrem >= 1.0:
                to_move += 1.0
                countrem -= 1.0

            if wards[play[i].ifrom].play_suscept < to_move:
                to_move = wards[play[i].ifrom].play_suscept

            wards[play[i].ifrom].play_suscept -= to_move
            links[i].suscept += to_move

    recalculate_work_denominator_day(network=network, params=params)
    recalculate_play_denominator_day(network=network, params=params)


def read_done_file(filename: str):
    """This function reads the 'done_file' from 'filename' returning the list
       of seeded nodes
    """
    try:
        print(f"{filename} -- ")

        nodes_seeded = []

        with open(filename, "r") as FILE:
            line = FILE.readline()

            # each line has a single number, which is the seed
            nodes_seeded.append( float(line.strip()) )

        return nodes_seeded

    except Exception as e:
        raise ValueError(f"Possible corruption of {filename}: {e}")


def recalculate_work_denominator_day(network: Network, params: Parameters):

    wards = network.nodes
    links = network.to_links

    sum = 0

    for i in range(1, network.nnodes+1):
        wards.denominator_d[i] = 0.0
        wards.denominator_n[i] = 0.0

    for j in range(1, network.nlinks+1):
        link = links[j]
        wards[link.ito].denominator_d += link.suscept
        wards[link.ifrom].denominator_n += link.suscept
        sum += link.suscept

    print(f"recalculate_work_denominator_day sum = {sum}")


def recalculate_play_denominator_day(network: Network, params: Parameters):

    wards = network.nodes
    links = network.play

    for i in range(1, network.nnodes+1):  # 1-indexed
        wards[i].denominator_pd = 0
        wards[i].denominator_p = 0

    sum = 0.0

    for j in range(1, network.plinks+1):  # 1-indexed
        link = links[j]
        denom = link.weight * wards[link.ifrom].play_suscept
        wards[link.ito].denominator_pd += denom

        sum += denom

    print(f"recalculate_play_denominator_day sum 1 = {sum}")

    sum = 0.0

    for i in range(1, network.nnodes+1):  # 1-indexed
        ward = wards[i]

        wards[i].denominator_pd = int(math.floor(ward.denominator_pd + 0.5))

        wards[i].denominator_p = ward.play_suscept

        if ward.play_suscept < 0.0:
            print(f"Negative play_suscept? {ward}")

        sum += wards[i].denominator_p

    print(f"recalculate_play_denominator_day sum 2 = {sum}")


def rescale_play_matrix(network: Network, params: Parameters):
    """ Static Play At Home rescaling.
	    for 1, everyone stays at home.
	    for 0 a lot of people move around.
    """

    links = network.play
    # nodes = network.nodes  # check if this is not needed in the code
                             # as it was declared in the original function

    if params.static_play_at_home > 0:
        # if we are making people stay at home, then do this loop through nodes
        # Rescale appropriately!
        sclfac = 1.0 - params.static_play_at_home

        for j in range(1, network.plinks+1):  # 1-indexed
            link = links[j]

            if link.ifrom != link.ito:
                # if it's not the home ward, then reduce the
                # number of play movers
                links[j].weight = link.suscept * sclfac
            else:
                # if it is the home ward
                links[j].weight = ((1.0 - link.suscept) * \
                                   params.static_play_at_home) + \
                                  link.suscept

    recalculate_play_denominator_day(network=network, params=params)


def reset_work_matrix(network: Network):
    links = network.to_links

    for i in range(1, network.nlinks+1):  # 1-indexed
        if links[i] is None:
            print(f"Missing a link at index {i}")
        else:
            links[i].suscept = links[i].weight


def reset_play_matrix(network: Network):
    links = network.play

    for i in range(1, network.plinks+1):  # 1-indexed
        if links[i] is None:
            print(f"Missing a play link at index {i}?")
        else:
            links[i].weight = links[i].suscept


def reset_play_susceptibles(network: Network):
    nodes = network.nodes

    for i in range(1, network.nnodes+1):  # 1-indexed
        if nodes[i] is None:
            print(f"Missing a node at index {i}?")
            # create a null node - need to check if this is the best thing
            # to do
            nodes[i] = Node()
        else:
            nodes[i].play_suscept = nodes[i].save_play_suscept


def reset_everything(network: Network, params: Parameters):
    reset_work_matrix(network)
    reset_play_matrix(network)
    reset_play_susceptibles(network)

    # if weekend
    #    reset_weekend_matrix(network)

    N_INF_CLASSES = params.disease_params.N_INF_CLASSES()

    params.disease_params.contrib_foi = N_INF_CLASSES * [0]

    for i in range(0, N_INF_CLASSES-1):   # why -1?
        params.disease_params.contrib_foi[i] = 1


def get_min_max_distances(network: Network):
    """Return the minimum and maximum distances recorded in the network"""
    mindist = None
    maxdist = None

    links = network.to_links

    for link in links:
        dist = link.distance

        if dist:
            if mindist is None:
                mindist = dist
                maxdist = dist
            elif dist > maxdist:
                maxdist = dist
            elif dist < mindist:
                mindist = dist

    print(f"maxdist {maxdist} mindist {mindist}")

    if mindist > 0:
        print(f"The original code always gives a minimum distance of zero, "
              f"so setting {mindist} to zero... (check if this is correct)")

    mindist = 0

    return (mindist, maxdist)


def initialise_infections(network: Network, params: Parameters):
    disease = params.disease_params

    n = disease.N_INF_CLASSES()

    infections = []

    nlinks = network.nlinks + 1

    for _ in range(0, n):
        infections.append( nlinks * [0] )

    return infections


def initialise_play_infections(network: Network, params: Parameters):
    disease = params.disease_params

    n = disease.N_INF_CLASSES()

    infections = []

    nnodes = network.nnodes + 1

    for _ in range(0, n):
        infections.append( nnodes * [0] )

    return infections


def fill_in_gaps(network: Network):
    """Fills in gaps in the network"""
    links = network.to_links

    added = 0

    for i in range(1, network.nlinks+1):  # careful of 1-indexing
        link_to = links.ito[i]
        if network.nodes.label[link_to] != link_to:
            print(f"ADDING LINK {i} {link_to} {network.nnodes}")
            network.nodes.label[link_to] = link_to
            network.nnodes += 1

            added += 1
            assert added < 20   # something if too many missing links


def build_play_matrix(network: Network, params: Parameters,
                      max_links: int):

    nlinks = 0
    links = ToLinks(max_links + 1)

    try:
        with open(params.input_files.play) as FILE:
            # resets the node label as a flag to check progress?
            for j in range(1, network.nnodes+1):
                network.nodes.label[j] = -1

            nodes = network.nodes

            line = FILE.readline()
            while line:
                words = line.split()
                from_id = int(words[0])
                to_id = int(words[1])
                weight = float(words[2])

                nlinks += 1

                if from_id == 0 or to_id == 0:
                    raise ValueError(
                                f"Zero in link list: ${from_id}-${to_id}! "
                                f"Renumber files and start again")

                if nodes.label[from_id] == -1:
                    nodes.label[from_id] = from_id
                    nodes.begin_p[from_id] = nlinks
                    nodes.end_p[from_id] = nlinks

                if from_id == to_id:
                    nodes.self_p[from_id] = nlinks

                nodes.end_p[from_id] += 1

                links.ifrom[nlinks] = from_id
                links.ito[nlinks] = to_id
                links.weight[nlinks] = weight

                nodes.denominator_p[from_id] += weight  # not denominator_p
                nodes.play_suscept[from_id] += weight

                line = FILE.readline()
    except Exception as e:
        raise ValueError(f"{params.input_files.play} is corrupted or "
                         f"unreadable? Error = {e.__class__}: {e}")

    renormalise = (params.input_files.play == params.input_files.work)

    for j in range(1, nlinks+1):   # careful 1-indexed
        if renormalise:
            links.weight[j] /= nodes.denominator_p[links.ifrom[j]]

        links.suscept[j] = links.weight[j]

    fill_in_gaps(network)

    try:
        with open(params.input_files.play_size, "r") as FILE:
            line = FILE.readline()

            while line:
                words = line.split()
                i1 = int(words[0])
                i2 = int(words[1])

                nodes.play_suscept[i1] = i2
                nodes.denominator_p[i1] = i2
                nodes.save_play_suscept[i1] = i2

                line = FILE.readline()

    except Exception as e:
        raise ValueError(f"{params.input_files.play_size} is corrupted or "
                         f"unreadable? Error = {e.__class__}: {e}")

    print(f"Number of play links equals {nlinks}")

    network.plinks = nlinks
    network.play = links


def build_wards_network(params: Parameters,
                        max_nodes:int = 10050,
                        max_links:int = 2414000):
    """Creates a network from a file (specified in par->WorkFname) with format:

        * Node_1 Node_2 weight 1-2
        * Node_3 Node_4 weight 3-4
        * Node_4 Node_1 weight 4-1
        * Node_2 Node_1 weight 2-1
        * ...

         BE CAREFUL!! Weights may not be symmetric, network is built with
         asymmetric links

        play=0 builds network from input file and NOTHING ELSE
        play=1 build the play matrix in net->play
    """
    nodes = Nodes(max_nodes + 1)     # need to pre-allocate nodes and links
    links = ToLinks(max_links + 1)   # both of these use 1-indexing

    nlinks = 0
    nnodes = 0

    line = None

    try:
        with open(params.input_files.work, "r") as FILE:
            # this file is a set of links of from and to node IDs, with weights
            line = FILE.readline()
            while line:
                words = line.split()
                from_id = int(words[0])
                to_id = int(words[1])
                weight = float(words[2])

                if from_id == 0 or to_id == 0:
                    raise ValueError(
                                f"Zero in link list: ${from_id}-${to_id}! "
                                f"Renumber files and start again")

                nlinks += 1

                if nodes.label[from_id] == -1:
                    nodes.label[from_id] = from_id
                    nodes.begin_to[from_id] = nlinks
                    nodes.end_to[from_id] = nlinks
                    nnodes += 1

                if from_id == to_id:
                    nodes.self_w[from_id] = nlinks

                nodes.end_to[from_id] += 1

                # original code does int(weight) even though this is a float?
                links.ifrom[nlinks] = from_id
                links.ito[nlinks] = to_id
                links.weight[nlinks] = int(weight)
                links.suscept[nlinks] = int(weight)

                # again, int(weight) is in the code despite these being floats?
                nodes.denominator_n[from_id] += int(weight)

                nodes.denominator_d[to_id] += int(weight)

                line = FILE.readline()
    except Exception as e:
        raise ValueError(f"{params.input_files.work} is corrupted or "
                         f"unreadable? line = {line}, "
                         f"Error = {e.__class__}: {e}")

    network = Network(nnodes=nnodes, nlinks=nlinks)

    network.nodes = nodes
    network.to_links = links

    print(f"Number of nodes equals {nnodes}")
    print(f"Number of links equals {nlinks}")

    fill_in_gaps(network)

    print(f"Number of nodes after filling equals {network.nnodes}")

    build_play_matrix(network=network, params=params, max_links=max_links)

    print(f"Number of nodes after build play equals {network.nnodes}")

    print(f"Resize nodes to {network.nnodes + 1}")
    network.nodes.resize(network.nnodes + 1)     # remember 1-indexed
    network.to_links.resize(network.nlinks + 1)  # remember 1-indexed
    network.play.resize(network.plinks + 1)      # remember 1-indexed

    return network


def build_wards_network_distance(params: Parameters):
    """Calls BuildWardsNetwork (as above), but adds extra bit, to
       read LocationFile and calculate distances of links, put them
       in net->to_links[i].distance
       Distances are not included in the play matrix
    """

    network = build_wards_network(params)

    # ncov build does not have WEEKEND defined, so not writing this code now

    wards = network.nodes
    links = network.to_links
    plinks = network.play

    line = None

    try:
        with open(params.input_files.position, "r") as FILE:
            line = FILE.readline()

            while line:
                words = line.split()
                i1 = int(words[0])
                x = float(words[1])
                y = float(words[2])

                wards.x[i1] = x
                wards.y[i1] = y

                line = FILE.readline()
    except Exception as e:
        raise ValueError(f"{params.input_files.position} is corrupted or "
                         f"unreadable? Error = {e.__class__}: {e}, "
                         f"line = {line}")

    total_distance = 0

    for i in range(0, network.nlinks):  # shouldn't this be range(1, nlinks+1)?
                                        # the fact there is a missing link at 0
                                        # suggests this should be...
        link = links[i]

        ward = wards[link.ifrom]
        x1 = ward.x
        y1 = ward.y

        ward = wards[link.ito]
        x2 = ward.x
        y2 = ward.y

        dx = x1 - x2
        dy = y1 - y2

        distance = math.sqrt(dx*dx + dy*dy)
        links.distance[i] = distance
        total_distance += distance

        # below line doesn't make sense and doesn't work. Why would the ith
        # play link be related to the ith work link?
        #plinks.distance[i] = distance

    print(f"Total distance equals {total_distance}")

    return network
