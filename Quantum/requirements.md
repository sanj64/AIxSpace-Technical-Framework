qiskit
pennylane
numpy
matplotlib

basic Python file to test if Qiskit installs correctly:

# Quantum/test_qiskit.py
from qiskit import Aer
print("Qiskit is working. Simulator backend:", Aer.backends())
