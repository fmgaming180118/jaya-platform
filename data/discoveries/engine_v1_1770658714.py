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
        out._backward = lambda: (self.__grad_add(other, out), other.__grad_add(self, out))
        return out

    def __grad_add(self, other, out):
        self.grad += out.grad

    def __mul__(self, other):
        other = other if isinstance(other, Value) else Value(other)
        out = Value(self.data * other.data, (self, other), '*')
        out._backward = lambda: (self.__grad_mul(other, out), other.__grad_mul(self, out))
        return out

    def __grad_mul(self, other, out):
        self.grad += other.data * out.grad

    def __pow__(self, other):
        assert isinstance(other, (int, float)), "only supporting int/float powers for now"
        out = Value(self.data**other, (self,), f'**{other}')
        out._backward = lambda: self.__grad_pow(other, out)
        return out

    def __grad_pow(self, other, out):
        self.grad += (other * self.data**(other-1)) * out.grad

    def __neg__(self):
        return self * -1

    def __sub__(self, other):
        return self + (-other)

    def __truediv__(self, other):
        return self * other**-1

    def tanh(self):
        t = math.tanh(self.data)
        out = Value(t, (self,), 'tanh')
        out._backward = lambda: self.__grad_tanh(t, out)
        return out

    def __grad_tanh(self, t, out):
        self.grad += (1 - t**2) * out.grad

    def exp(self):
        out = Value(math.exp(self.data), (self,), 'exp')
        out._backward = lambda: self.__grad_exp(out)
        return out

    def __grad_exp(self, out):
        self.grad += out.data * out.grad

    def log(self):
        out = Value(math.log(self.data), (self,), 'log')
        out._backward = lambda: self.__grad_log(out)
        return out

    def __grad_log(self, out):
        self.grad += (1/self.data) * out.grad

    def relu(self):
        out = Value(max(0, self.data), (self,), 'ReLU')
        out._backward = lambda: self.__grad_relu(out)
        return out

    def __grad_relu(self, out):
        self.grad += (out.data > 0) * out.grad

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