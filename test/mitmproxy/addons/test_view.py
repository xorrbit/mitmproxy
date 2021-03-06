from mitmproxy.test import tflow
from mitmproxy.addons import view
from mitmproxy import flowfilter
from mitmproxy import options
from mitmproxy.test import taddons

from .. import tutils


class Options(options.Options):
    def __init__(
        self, *,
        filter=None,
        order=None,
        order_reversed=False,
        **kwargs
    ):
        self.filter = filter
        self.order = order
        self.order_reversed = order_reversed
        super().__init__(**kwargs)


def test_simple():
    v = view.View()
    f = tflow.tflow()
    f.request.timestamp_start = 1
    v.request(f)
    assert list(v) == [f]
    v.request(f)
    assert list(v) == [f]
    assert len(v._store) == 1

    f2 = tflow.tflow()
    f2.request.timestamp_start = 3
    v.request(f2)
    assert list(v) == [f, f2]
    v.request(f2)
    assert list(v) == [f, f2]
    assert len(v._store) == 2

    f3 = tflow.tflow()
    f3.request.timestamp_start = 2
    v.request(f3)
    assert list(v) == [f, f3, f2]
    v.request(f3)
    assert list(v) == [f, f3, f2]
    assert len(v._store) == 3

    v.clear()
    assert len(v) == 0
    assert len(v._store) == 0


def tft(*, method="get", start=0):
    f = tflow.tflow()
    f.request.method = method
    f.request.timestamp_start = start
    return f


def test_filter():
    v = view.View()
    f = flowfilter.parse("~m get")
    v.request(tft(method="get"))
    v.request(tft(method="put"))
    v.request(tft(method="get"))
    v.request(tft(method="put"))
    assert(len(v)) == 4
    v.set_filter(f)
    assert [i.request.method for i in v] == ["GET", "GET"]
    assert len(v._store) == 4
    v.set_filter(None)

    assert len(v) == 4
    v[1].marked = True
    v.toggle_marked()
    assert len(v) == 1
    assert v[0].marked
    v.toggle_marked()
    assert len(v) == 4


def test_order():
    v = view.View()
    with taddons.context(options=Options()) as tctx:
        v.request(tft(method="get", start=1))
        v.request(tft(method="put", start=2))
        v.request(tft(method="get", start=3))
        v.request(tft(method="put", start=4))
        assert [i.request.timestamp_start for i in v] == [1, 2, 3, 4]

        tctx.configure(v, order="method")
        assert [i.request.method for i in v] == ["GET", "GET", "PUT", "PUT"]
        v.set_reversed(True)
        assert [i.request.method for i in v] == ["PUT", "PUT", "GET", "GET"]

        tctx.configure(v, order="time")
        assert [i.request.timestamp_start for i in v] == [4, 3, 2, 1]

        v.set_reversed(False)
        assert [i.request.timestamp_start for i in v] == [1, 2, 3, 4]


def test_reversed():
    v = view.View()
    v.request(tft(start=1))
    v.request(tft(start=2))
    v.request(tft(start=3))
    v.set_reversed(True)

    assert v[0].request.timestamp_start == 3
    assert v[-1].request.timestamp_start == 1
    assert v[2].request.timestamp_start == 1
    tutils.raises(IndexError, v.__getitem__, 5)
    tutils.raises(IndexError, v.__getitem__, -5)

    assert v.bisect(v[0]) == 1
    assert v.bisect(v[2]) == 3


def test_update():
    v = view.View()
    flt = flowfilter.parse("~m get")
    v.set_filter(flt)

    f = tft(method="get")
    v.request(f)
    assert f in v

    f.request.method = "put"
    v.update(f)
    assert f not in v

    f.request.method = "get"
    v.update(f)
    assert f in v

    v.update(f)
    assert f in v


class Record:
    def __init__(self):
        self.calls = []

    def __bool__(self):
        return bool(self.calls)

    def __repr__(self):
        return repr(self.calls)

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))


def test_signals():
    v = view.View()
    rec_add = Record()
    rec_update = Record()
    rec_remove = Record()
    rec_refresh = Record()

    def clearrec():
        rec_add.calls = []
        rec_update.calls = []
        rec_remove.calls = []
        rec_refresh.calls = []

    v.sig_add.connect(rec_add)
    v.sig_update.connect(rec_update)
    v.sig_remove.connect(rec_remove)
    v.sig_refresh.connect(rec_refresh)

    assert not any([rec_add, rec_update, rec_remove, rec_refresh])

    # Simple add
    v.add(tft())
    assert rec_add
    assert not any([rec_update, rec_remove, rec_refresh])

    # Filter change triggers refresh
    clearrec()
    v.set_filter(flowfilter.parse("~m put"))
    assert rec_refresh
    assert not any([rec_update, rec_add, rec_remove])

    v.set_filter(flowfilter.parse("~m get"))

    # An update that results in a flow being added to the view
    clearrec()
    v[0].request.method = "PUT"
    v.update(v[0])
    assert rec_remove
    assert not any([rec_update, rec_refresh, rec_add])

    # An update that does not affect the view just sends update
    v.set_filter(flowfilter.parse("~m put"))
    clearrec()
    v.update(v[0])
    assert rec_update
    assert not any([rec_remove, rec_refresh, rec_add])

    # An update for a flow in state but not view does not do anything
    f = v[0]
    v.set_filter(flowfilter.parse("~m get"))
    assert not len(v)
    clearrec()
    v.update(f)
    assert not any([rec_add, rec_update, rec_remove, rec_refresh])


def test_focus():
    # Special case - initialising with a view that already contains data
    v = view.View()
    v.add(tft())
    f = view.Focus(v)
    assert f.index is 0
    assert f.flow is v[0]

    # Start empty
    v = view.View()
    f = view.Focus(v)
    assert f.index is None
    assert f.flow is None

    v.add(tft(start=1))
    assert f.index == 0
    assert f.flow is v[0]

    v.add(tft(start=0))
    assert f.index == 1
    assert f.flow is v[1]

    v.add(tft(start=2))
    assert f.index == 1
    assert f.flow is v[1]

    v.remove(v[1])
    assert f.index == 1
    assert f.flow is v[1]

    v.remove(v[1])
    assert f.index == 0
    assert f.flow is v[0]

    v.remove(v[0])
    assert f.index is None
    assert f.flow is None

    v.add(tft(method="get", start=0))
    v.add(tft(method="get", start=1))
    v.add(tft(method="put", start=2))
    v.add(tft(method="get", start=3))

    f.flow = v[2]
    assert f.flow.request.method == "PUT"

    filt = flowfilter.parse("~m get")
    v.set_filter(filt)
    assert f.index == 2

    filt = flowfilter.parse("~m oink")
    v.set_filter(filt)
    assert f.index is None


def test_settings():
    v = view.View()
    f = tft()

    tutils.raises(KeyError, v.settings.__getitem__, f)
    v.add(f)
    v.settings[f]["foo"] = "bar"
    assert v.settings[f]["foo"] == "bar"
    assert len(list(v.settings)) == 1
    v.remove(f)
    tutils.raises(KeyError, v.settings.__getitem__, f)
    assert not v.settings.keys()


def test_configure():
    v = view.View()
    with taddons.context(options=Options()) as tctx:
        tctx.configure(v, filter="~q")
        tutils.raises("invalid interception filter", tctx.configure, v, filter="~~")

        tctx.configure(v, order="method")
        tutils.raises("unknown flow order", tctx.configure, v, order="no")

        tctx.configure(v, order_reversed=True)
