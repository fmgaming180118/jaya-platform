
import math
from numba import jit, float64, int64
import numpy as np

# Standalone JIT functions for heavy lifting
@jit(nopython=True)
def jit_add_backward(grad_out):
    return 1.0 * grad_out, 1.0 * grad_out

@jit(nopython=True)
def jit_mul_backward(self_data, other_data, grad_out):
    return other_data * grad_out, self_data * grad_out

@jit(nopython=True)
def jit_pow_backward(self_data, other_data, grad_out):
    # grad_self = (other * self**(other-1)) * grad_out
    return (other_data * self_data**(other_data-1)) * grad_out

@jit(nopython=True)
def jit_relu_backward(data, grad_out):
    return (data > 0) * grad_out

@jit(nopython=True)
def jit_tanh_backward(t, grad_out):
    return (1 - t**2) * grad_out

@jit(nopython=True)
def jit_exp_backward(out_data, grad_out):
    return out_data * grad_out

@jit(nopython=True)
def jit_log_backward(self_data, grad_out):
    return (1/self_data) * grad_out


class Value:
    __slots__ = ['data', 'grad', '_backward', '_prev', '_op', 'label']

    def __init__(self, data, _children=(), _op='', label=''):
        self.data = float(data)
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
        
        def _backward():
            # Call JIT function
            g1, g2 = jit_add_backward(out.grad)
            self.grad += g1
            other.grad += g2
        out._backward = _backward
        return out

    def __mul__(self, other):
        other = other if isinstance(other, Value) else Value(other)
        out = Value(self.data * other.data, (self, other), '*')
        
        def _backward():
            g1, g2 = jit_mul_backward(self.data, other.data, out.grad)
            self.grad += g1
            other.grad += g2
        out._backward = _backward
        return out

    def __pow__(self, other):
        assert isinstance(other, (int, float))
        out = Value(self.data**other, (self,), f'**{other}')
        
        def _backward():
            self.grad += jit_pow_backward(self.data, other, out.grad)
        out._backward = _backward
        return out

    def relu(self):
        out = Value(max(0, self.data), (self,), 'ReLU')
        def _backward():
            self.grad += jit_relu_backward(out.data, out.grad)
        out._backward = _backward
        return out

    def tanh(self):
        # We can also JIT the forward pass math if complex
        t = math.tanh(self.data)
        out = Value(t, (self,), 'tanh')
        def _backward():
            self.grad += jit_tanh_backward(t, out.grad)
        out._backward = _backward
        return out

    def exp(self):
        out = Value(math.exp(self.data), (self,), 'exp')
        def _backward():
            self.grad += jit_exp_backward(out.data, out.grad)
        out._backward = _backward
        return out

    def log(self):
        out = Value(math.log(self.data), (self,), 'log')
        def _backward():
            self.grad += jit_log_backward(self.data, out.grad)
        out._backward = _backward
        return out
        
    def __neg__(self): return self * -1
    def __sub__(self, other): return self + (-other)
    def __truediv__(self, other): return self * other**-1

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
