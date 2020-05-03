
from dataclasses import dataclass as _dataclass
from typing import Union as _Union

from ._network import Network
from ._networks import Networks

__all__ = ["Infections"]


@_dataclass
class Infections:
    """This class holds the arrays that record the infections as they
       are occuring during the outbreak
    """

    #: The infections caused by fixed (work) movements. This is a list
    #: of int arrays, size work[N_INF_CLASSES][nlinks+1]
    work = None

    #: The infections caused by random (play) movements. This is a list
    #: of int arrays, size play[N_INF_CLASSES][nnodes+1]
    play = None

    #: The infections for the multi-demographic subnets
    subinfs = None

    @staticmethod
    def build(network: _Union[Network, Networks] = None):
        """Construct and return the Infections object that will track
           infections during a model run on the passed Network (or Networks)

           Parameters
           ----------
           network: Network or Networks
             The network or networks that will be run

           Returns
           -------
           infections: Infections
             The space for the work and play infections for the network
             (including space for all of the demographics)
        """
        from .utils import initialise_infections, initialise_play_infections

        if isinstance(network, Network):
            inf = Infections()
            inf.work = initialise_infections(network=network)
            inf.play = initialise_play_infections(network=network)

            return inf

        elif isinstance(network, Networks):
            inf = Infections.build(network.overall)

            subinfs = []

            for subnet in network.subnets:
                subinfs.append(Infections.build(subnet))

            inf.subinfs = subinfs

            return inf

    def clear(self, nthreads: int = 1):
        """Clear all of the infections (resets all to zero)

           Parameters
           ----------
           nthreads: int
             Optionally parallelise this reset by specifying the number
             of threads to use
        """
        from .utils import clear_all_infections
        clear_all_infections(infections=self.work,
                             play_infections=self.play,
                             nthreads=nthreads)

        if self.subinfs is not None:
            for subinf in self.subinfs:
                subinf.clear(nthreads=nthreads)
