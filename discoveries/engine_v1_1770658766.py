import math
from functools import reduce

class Value:
    __slots__ = ['data', 'grad', '_backward', '_prev', '_op', 'label']

    def __init__(self, data, _children=(), _op='', label=''):
        self.data = data
        self.grad = 0.0
        self._backward = lambda: None
        self._prev = set(_children)
        self._op = _op
        self.label = label

    def __repr__(self):
        return f"Value(data={self.data})"

    def __add__(self, other):
        other = other if isinstance(other, Value) else Value(other)
        out = Value(self.data + other.data, (self, other), '+')
        out._backward = lambda: (self.grad += out.grad, other.grad += out.grad)
        return out

    def __mul__(self, other):
        other = other if isinstance(other, Value) else Value(other)
        out = Value(self.data * other.data, (self, other), '*')
        out._backward = lambda: (self.grad += other.data * out.grad, other.grad += self.data * out.grad)
        return out

    def __pow__(self, other):
        assert isinstance(other, (int, float)), "only supporting int/float powers for now"
        out = Value(self.data**other, (self,), f'**{other}')
        out._backward = lambda: self.grad += (other * self.data**(other-1)) * out.grad
        return out

    def __neg__(self):
        return self * -1

    def __sub__(self, other):
        return self + (-other)

    def __truediv__(self, other):
        return self * other**-1

    def tanh(self):
        t = math.tanh(self.data)
        out = Value(t, (self,), 'tanh')
        out._backward = lambda: self.grad += (1 - t**2) * out.grad
        return out

    def exp(self):
        out = Value(math.exp(self.data), (self,), 'exp')
        out._backward = lambda: self.grad += out.data * out.grad
        return out

    def log(self):
        out = Value(math.log(self.data), (self,), 'log')
        out._backward = lambda: self.grad += (1/self.data) * out.grad
        return out

    def relu(self):
        out = Value(max(0, self.data), (self,), 'ReLU')
        out._backward = lambda: self.grad += (out.data > 0) * out.grad
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
    e = a*b; e.label = 'e'
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