"""CSTR (Continuous Stirred Tank Reactor) nonlinear ODE.

States (x):
  c  - concentration of A      [mol/L]
  T  - reactor temperature     [K]
  h  - liquid level            [m]

Inputs (u):
  Tc - coolant temperature     [K]
  F  - outlet flow rate        [kL/min]

Disturbance (d):
  F0 - inlet flow rate         [kL/min]

The ODE uses CasADi-compatible math (ca.exp instead of np.exp) so the
SAME function can be evaluated:
  - numerically at runtime (returns DM, convert to array as needed)
  - symbolically by Layer 3 NLP (CasADi auto-diff for IPOPT gradients)

Source: mpc-tools-casadi reference (Rawlings group)
"""
import numpy as np
import casadi as ca

# Plant parameters
T0 = 350.0      # Inlet temperature (K)
c0 = 1.0        # Inlet concentration (mol/L)
r = 0.219       # Tank radius (m)
k0 = 7.2e10     # Arrhenius pre-exponential factor (1/min)
E = 8750.0      # Activation energy (K)
U = 54.94       # Heat transfer coefficient (kW/(m²·K))
rho = 1000.0    # Density (kg/m³)
Cp = 0.239      # Heat capacity (kJ/(kg·K))
dH = -5.0e4     # Heat of reaction (kJ/kmol)
A_cross = np.pi * r * r


def cstr_ode(x, u, d):
    """Continuous-time CSTR ODE: dx/dt = f(x, u, d).

    All values in engineering units.
    Works with both numpy arrays (numeric) and CasADi symbols (NLP).
    """
    c = x[0]
    T = x[1]
    h = x[2]
    Tc = u[0]
    F = u[1]
    F0 = d[0] if (hasattr(d, '__len__') and len(d) > 0) else 0.1

    rate = k0 * c * ca.exp(-E / T)

    dcdt = F0 * (c0 - c) / (A_cross * h) - rate
    dTdt = (F0 * (T0 - T) / (A_cross * h)
            - (dH / (rho * Cp)) * rate
            + (2 * U / (r * rho * Cp)) * (Tc - T))
    dhdt = (F0 - F) / A_cross

    # Return type depends on input type:
    #  - numpy/float inputs -> CasADi DM (we cast to array in plant.py)
    #  - CasADi MX/SX -> CasADi expression
    if isinstance(x, np.ndarray):
        # Numeric path: return numpy array
        return np.array([float(dcdt), float(dTdt), float(dhdt)])
    else:
        # Symbolic path: return CasADi vertcat
        return ca.vertcat(dcdt, dTdt, dhdt)
