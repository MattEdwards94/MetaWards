from __future__ import annotations

from array import array as _array

from .._network import PersonType

__all__ = ["MoveRecord"]


class MoveRecord:
    """This class holds a record of mover-initiated moves. This could
       be used, to reverse moves, e.g. to send individuals back from
       home hospital, or to send individuals back home from holiday
    """

    def __init__(self):
        self._record = []

    def add(self,
            from_stage: int, to_stage: int,
            from_type: PersonType, to_type: PersonType,
            from_ward_begin: int, from_ward_end: int,
            to_ward_begin: int, to_ward_end: int,
            from_demographic: int = 0, to_demographic: int = 0,
            number: int = 1):
        """Record the move from the specified demographic, stage
           type and ward to the specified demographic, stage,
           type and ward, recording the number of individuals
           who made this move.

           If the type is PLAYER, then the ward is the ward index
           If the type is WORKER, then the ward is the link index

           Need to specify both the begin and end index as, for
           workers, it may be a range of links, e.g.
           from_ward_begin=3, from_ward_end=4 would refer
           to range(3, 4) == ward index 3.
        """
        r = _array("i", (int(from_demographic), int(from_stage),
                         int(from_type.value), int(from_ward_begin),
                         int(from_ward_end),
                         int(to_demographic), int(to_stage),
                         int(to_type.value), int(to_ward_begin),
                         int(to_ward_end),
                         int(number)))
        self._record.append(r)

    def __len__(self):
        return len(self._record)

    def __getitem__(self, i: int) -> _array:
        return self._record[i]

    def __str__(self):
        return f"MoveRecord(count={len(self)})"

    def invert(self) -> MoveRecord:
        """Return a copy of this record with the moves inverted - i.e.
           a move of X -> Y of 10 individuals will become a move
           from Y -> X of 10 individuals. Use this, together with
           MoveGenerator, to reverse moves
        """
        inverted = MoveRecord()

        for r in self._record:
            (from_demographic, from_stage, from_type,
             from_ward_begin, from_ward_end,
             to_demographic, to_stage, to_type,
             to_ward_begin, to_ward_end, number) = r

            inverted.add(from_demographic=to_demographic,
                         from_stage=to_stage,
                         from_type=PersonType(to_type),
                         from_ward_begin=to_ward_begin,
                         from_ward_end=to_ward_end,
                         to_demographic=from_demographic,
                         to_stage=from_stage,
                         to_type=PersonType(from_type),
                         to_ward_begin=from_ward_begin,
                         to_ward_end=from_ward_end,
                         number=number)

        return inverted
