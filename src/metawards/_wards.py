
from typing import List as _List
from typing import Union as _Union

from .utils._profiler import Profiler, NullProfiler

from ._ward import Ward
from ._wardinfo import WardInfos, WardInfo

__all__ = ["Wards"]


class Wards:
    """This class holds an entire network of Ward objects"""

    def __init__(self, wards: _List[Ward] = None):
        """Construct, optionally from a list of Ward objects"""
        self._wards = []
        self._info = WardInfos()

        self._unresolved = []

        if wards is not None:
            self.insert(wards)

    def __str__(self):
        if len(self) == 0:
            return "Wards::null"
        elif len(self) < 10:
            return f"[ {', '.join([str(x) for x in self._wards[1:]])} ]"
        else:
            s = f"[ {', '.join([str(x) for x in self._wards[1:7]])}, ... "
            s += f"{', '.join([str(x) for x in self._wards[-3:]])} ]"

            return s

    def __eq__(self, other):
        return self.__class__ == other.__class__ and \
            self.__dict__ == other.__dict__

    def insert(self, wards: _List[Ward]) -> None:
        """Append the passed wards onto this list"""
        if not isinstance(wards, list):
            wards = [wards]

        for ward in wards:
            if isinstance(ward, Wards):
                for w in ward:
                    if w is not None:
                        w.dereference(ward)
                        self.insert(w)
            elif ward is None:
                continue
            elif not isinstance(ward, Ward):
                raise TypeError(
                    f"You cannot append a {ward} to a list of Ward objects!")

        # get the largest ID and then resize the list...
        largest_id = 0

        for ward in wards:
            if isinstance(ward, Ward):
                if ward.id() is not None and ward.id() > largest_id:
                    largest_id = ward.id()

        if largest_id >= len(self._wards):
            self._wards += [None] * (largest_id - len(self._wards) + 1)

        add_later = []

        from copy import deepcopy

        for ward in wards:
            if isinstance(ward, Ward):
                # make sure that this is not a duplicate...
                info = ward._info

                if info in self._info:
                    idx = self._info.index(info)
                    if idx != ward.id():
                        raise KeyError(
                            f"You cannot have two different wards that have "
                            f"the same info: {self._wards[idx]} : {ward}")
                    # otherwise the IDs are the same, so this is an
                    # update to an existing ward

                if ward.id() is None:
                    add_later.append(ward)
                else:
                    ward = deepcopy(ward)
                    self._wards[ward.id()] = ward
                    self._info[ward.id()] = ward._info
                    self._unresolved.append(ward.id())

        for ward in add_later:
            # append this onto the end of the list
            idx = len(self._wards)
            ward = deepcopy(ward)
            ward.set_id(idx)
            self._wards.append(ward)
            self._info[ward.id()] = ward._info
            self._unresolved.append(ward.id())

        self._resolve()

    def add(self, ward: Ward) -> None:
        """Synonym for insert"""
        self.insert(ward)

    def __add__(self, other):
        from copy import deepcopy
        c = deepcopy(self)
        c.add(other)
        return c

    def __radd__(self, other):
        return self.__add__(other)

    def __iadd__(self, other):
        self.add(other)
        return self

    def is_resolved(self) -> bool:
        """Return whether or not this is a fully resolved set of Wards
           (i.e. each ward only links to other wards in this set)
        """
        return len(self._unresolved) == 0

    def unresolved_wards(self) -> _List[int]:
        """Return the list of IDs of unresolved wards"""
        from copy import deepcopy
        return deepcopy(self._unresolved)

    def _resolve(self) -> None:
        """Try to resolve all of the links. Note that this will only resolve
           as many wards as it can. Any unresolved wards will be available
           as 'unresolvd_wards'
        """
        still_unresolved = []

        for unresolved in self._unresolved:
            self._wards[unresolved].resolve(self)

            if not self._wards[unresolved].is_resolved():
                still_unresolved.append(unresolved)

        self._unresolved = still_unresolved

    def get(self, id: _Union[int, WardInfo], dereference: bool = True) -> Ward:
        """Return the ward with the specified id - this can eb the integer
           ID of the ward or the WardInfo of the ward. If 'dereference'
           is True then this will dereference all of the IDs into
           WardInfo objects. This is useful if you want to use the
           resulting Ward with other Wards collections
        """
        ward = self[id]

        if dereference:
            ward.dereference(self)

        return ward

    def getinfo(self, id: _Union[int, str, WardInfo]) -> WardInfo:
        """Return the WardInfo matching the ward with the passed ID"""
        idx = self.index(id)
        return self._info.wards[idx]

    def __getitem__(self, id: _Union[int, str, WardInfo]) -> Ward:
        """Return the ward with specified id - this can be the integer
           ID of the ward, or the WardInfo of the ward. Note that
           this returns a copy of the Ward
        """
        if isinstance(id, Ward):
            idx = self._info.index(id._info)

            if id._id is not None:
                if idx != id._id:
                    return ValueError(f"No ward matching {id}")

            w = self._wards[idx]
        elif isinstance(id, WardInfo):
            w = self._wards[self._info.index(id)]
        elif isinstance(id, str):
            try:
                return self[int(id)]
            except Exception:
                pass

            return self[WardInfo(name=id)]
        else:
            w = self._wards[id]

        # must deepcopy this or else it can be changed behind our back
        from copy import deepcopy
        return deepcopy(w)

    def index(self, id: _Union[int, str, WardInfo, Ward]) -> int:
        """Return the index of the ward that matches the passed
           id - which can be the integer ID or WardInfo - in this
           Wards object. This raises a ValueError if the
           ward doens't exist
        """
        if isinstance(id, Ward):
            return self._info.index(id._info)
        elif isinstance(id, WardInfo):
            return self._info.index(id)
        elif isinstance(id, str):
            try:
                return self.index(int(id))
            except Exception:
                pass

            return self.index(WardInfo(name=id))
        else:
            try:
                id = int(id)
            except Exception:
                raise ValueError(f"No ward matching {id}")

            if id < 0:
                id = len(self._wards) + id

            if id < 0 or id >= len(self._wards):
                raise ValueError(f"No ward matching {id}")

            if self._wards[id] is None:
                raise ValueError(f"No ward matching {id}")

            return id

    def __contains__(self, id: _Union[int, str, WardInfo, Ward]) -> bool:
        """Return whether or not the passed id - which can be an integer
           ID or WardInfo - is in this Wards object
        """
        if isinstance(id, Ward):
            return id._info in self._info
        elif isinstance(id, WardInfo):
            return id in self._info
        elif isinstance(id, str):
            try:
                if self.__contains__(int(id)):
                    return True
            except Exception:
                pass

            return self.__contains__(WardInfo(name=id))
        else:
            id = int(id)

            if id < 0:
                id = len(self._wards) + id

            if id < 0 or id >= len(self._wards):
                return False
            else:
                return self._wards[id] is not None

    def contains(self, id: _Union[int, str, WardInfo]) -> bool:
        """Return whether or not the passed id - which can be an integer
           ID or WardInfo - is in this Wards object
        """
        return self.__contains__(id)

    def __len__(self):
        return len(self._wards)

    def num_work_links(self):
        """Return the total number of work links"""
        n = 0

        for ward in self._wards:
            if ward is not None:
                n += ward.num_work_links()

        return n

    def num_play_links(self):
        """Return the total number of play links"""
        n = 0

        for ward in self._wards:
            if ward is not None:
                n += ward.num_play_links()

        return n

    def num_players(self):
        """Return the total number of players in this network"""
        num = 0

        for ward in self._wards:
            if ward is not None:
                num += ward.num_players()

        return num

    def num_workers(self):
        """Return the total number of workers in this network"""
        num = 0

        for ward in self._wards:
            if ward is not None:
                num += ward.num_workers()

        return num

    def population(self):
        """Return the total population in this network"""
        num = 0

        for ward in self._wards:
            if ward is not None:
                num += ward.population()

        return num

    def assert_sane(self):
        """Make sure that we don't refer to any non-existent wards"""
        if len(self._wards) == 0:
            return

        self._resolve()

        nwards = len(self._wards) - 1

        for i, ward in enumerate(self._wards):
            if ward is None:
                continue

            if i != ward.id():
                raise AssertionError(f"{ward} should have index {i}")

            for c in ward.work_connections():
                if not isinstance(c, int):
                    raise AssertionError(f"Unresolved connection {c}")
                elif c < 1 or c > nwards:
                    raise AssertionError(
                        f"{ward} has a work connection to an invalid "
                        f"ward ID {c}. Range should be 1 <= n <= {nwards}")
                elif self._wards[c] is None:
                    raise AssertionError(
                        f"{ward} has a work connection to a null "
                        f"ward ID {c}. This ward is null")

            for c in ward.play_connections():
                if not isinstance(c, int):
                    raise AssertionError(f"Unresolved connection {c}")
                elif c < 1 or c > nwards:
                    raise AssertionError(
                        f"{ward} has a play connection to an invalid "
                        f"ward ID {c}. Range should be 1 <= n <= {nwards}")
                elif self._wards[c] is None:
                    raise AssertionError(
                        f"{ward} has a play connection to a null "
                        f"ward ID {c}. This ward is null")

    def to_data(self, profiler: Profiler = None):
        """Return a data representation of these wards that can
           be serialised to JSON
        """
        if len(self) > 0:
            if profiler is None:
                profiler = NullProfiler()

            p = profiler.start("to_data")
            p = p.start("assert_sane")
            self.assert_sane()
            p = p.stop()

            p = p.start("convert_wards")

            nwards = len(self._wards)

            from .utils._console import Console
            with Console.progress(visible=(nwards > 250)) as progress:
                data = []
                task = progress.add_task("Converting to data", total=nwards)

                for i, ward in enumerate(self._wards):
                    if ward is None:
                        continue
                    else:
                        data.append(ward.to_data())

                    if i % 250 == 0:
                        progress.update(task, completed=i+1)

                progress.update(task, completed=nwards, force_update=True)

            p = p.stop()
            p = p.stop()

            return data

        else:
            return None

    @staticmethod
    def from_data(data, profiler: Profiler = None):
        """Return the Wards constructed from a data represnetation,
           which may have come from deserialised JSON
        """
        if data is None or len(data) == 0:
            return Wards()

        if profiler is None:
            profiler = NullProfiler()

        p = profiler.start("from_data")

        p = p.start("convert_wards")
        wards = Wards()

        nwards = len(data)

        from .utils._console import Console
        with Console.progress(visible=(nwards > 250)) as progress:
            task = progress.add_task("Converting from data", total=nwards)

            for i, x in enumerate(data):
                if x is not None:
                    wards.insert(Ward.from_data(x))

                if i % 250 == 0:
                    progress.update(task, completed=i+1)

            progress.update(task, completed=nwards, force_update=True)

        p = p.stop()

        p = p.start("assert_sane")
        wards.assert_sane()
        p = p.stop()

        p = p.stop()

        return wards

    def to_json(self, filename: str = None, indent: int = None,
                auto_bzip: bool = True) -> str:
        """Serialise the wards to JSON. This will write to a file
           if filename is set, otherwise it will return a JSON string.

           Parameters
           == == == == ==
           filename: str
             The name of the file to write the JSON to. The absolute
             path to the written file will be returned. If filename is None
             then this will serialise to a JSON string which will be
             returned.
           indent: int
             The number of spaces of indent to use when writing the json
           auto_bzip: bool
             Whether or not to automatically bzip2 the written json file

           Returns
           == == == =
           str
             Returns either the absolute path to the written file, or
             the json-serialised string
        """
        import json

        if indent is not None:
            indent = int(indent)

        if filename is None:
            return json.dumps(self.to_data(), indent=indent)
        else:
            from pathlib import Path
            filename = str(Path(filename).expanduser().resolve().absolute())

            if auto_bzip:
                if not filename.endswith(".bz2"):
                    filename += ".bz2"

                import bz2
                with bz2.open(filename, "wt") as FILE:
                    try:
                        json.dump(self.to_data(), FILE, indent=indent)
                    except Exception:
                        import os
                        FILE.close()
                        os.unlink(filename)
                        raise
            else:
                with open(filename, "w") as FILE:
                    try:
                        json.dump(self.to_data(), FILE, indent=indent)
                    except Exception:
                        import os
                        FILE.close()
                        os.unlink(filename)
                        raise

            return filename

    @staticmethod
    def from_json(s: str):
        """Return the Wards constructed from the passed json. This will
           either load from a passed json string, or from json loaded
           from the passed file
        """
        import os
        import json

        if os.path.exists(s):
            try:
                import bz2
                with bz2.open(s, "rt") as FILE:
                    data = json.load(FILE)
            except Exception:
                data = None

            if data is None:
                with open(s, "rt") as FILE:
                    data = json.load(FILE)
        else:
            data = json.loads(s)

        return Wards.from_data(data)
