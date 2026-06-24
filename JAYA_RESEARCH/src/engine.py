import math
from numba import njit

# Fallback if Numba is not available
try:
    _njit = njit
except ImportError:  # pragma: no cover
    def _njit(func):
        return func

@_njit
def _tanh(x):
    return math.tanh(x)

@_njit
def _exp(x):
    return math.exp(x)

@_njit
def _log(x):
    return math.log(x)

@_njit
def _relu(x):
    return x if x > 0.0 else 0.0

class Value:
    __slots__ = ['data', 'grad', '_backward', '_prev', '_op', 'label']

    def __init__(self, data, _children=(), _op='', label=''):
        self.data = float(data)
        self.grad = 0.0
        self._backward = lambda: None
        self._prev = _children
        self._op = _op
        self.label = label

    def __repr__(self):
        return f"Value(data={self.data})"

    def __add__(self, other):
        other = other if isinstance(other, Value) else Value(other)
        out = Value(self.data + other.data, (self, other), '+')
        def _backward():
            self.grad += out.grad
            other.grad += out.grad
        out._backward = _backward
        return out

    def __radd__(self, other):
        return self.__add__(other)

    def __mul__(self, other):
        other = other if isinstance(other, Value) else Value(other)
        out = Value(self.data * other.data, (self, other), '*')
        def _backward():
            self.grad += other.data * out.grad
            other.grad += self.data * out.grad
        out._backward = _backward
        return out

    def __rmul__(self, other):
        return self.__mul__(other)

    def __pow__(self, other):
        assert isinstance(other, (int, float)), "only supporting int/float powers for now"
        out = Value(self.data ** other, (self,), f'**{other}')
        def _backward():
            self.grad += other * self.data ** (other - 1) * out.grad
        out._backward = _backward
        return out

    def __rpow__(self, other):
        return Value(other) ** self

    def tanh(self):
        t = _tanh(self.data)
        out = Value(t, (self,), 'tanh')
        def _backward():
            self.grad += (1.0 - t * t) * out.grad
        out._backward = _backward
        return out

    def exp(self):
        e = _exp(self.data)
        out = Value(e, (self,), 'exp')
        def _backward():
            self.grad += out.data * out.grad
        out._backward = _backward
        return out

    def log(self):
        l = _log(self.data)
        out = Value(l, (self,), 'log')
        def _backward():
            self.grad += out.grad / self.data
        out._backward = _backward
        return out

    def relu(self):
        r = _relu(self.data)
        out = Value(r, (self,), 'ReLU')
        def _backward():
            self.grad += (out.data > 0.0) * out.grad
        out._backward = _backward
        return out

    def backward(self):
        topo = []
        visited = set()
        def build_topo(v):
            if v not in visited:
                visited.add(v)
                for child in v._prev:
                    build_topo(child)
                topo.append(v)
        build_topo(self)
        self.grad = 1.0
        for node in reversed(topo):
            node._backward()

    def numpy(self):
        return self.data

if __name__ == "__main__":
    a = Value(2.0, label='a')
    b = Value(-3.0, label='b')
    c = Value(10.0, label='c')
    e = a * b; e.label = 'e'
    d = e + c; d.label = 'd'
    f = Value(-2.0, label='f')
    L = d * f; L.label = 'L'
    L.backward()
    print(f"L.data: {L.data}")
    print(f"a.grad: {a.grad}")
    if abs(L.data - (-8.0)) < 0.001 and abs(a.grad - 6.0) < 0.001:
        print("[SUCCESS] Engine works.")
    else:
        print("[FAIL] Gradients mismatch.")