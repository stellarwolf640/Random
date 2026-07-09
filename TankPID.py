import numpy as np
import matplotlib.pyplot as plt

# Simulation parameters
dt = 0.1
time = np.arange(0, 50, dt)

# Tank parameters
A = 1.0          # Cross-sectional area
outflow_coeff = 3  # Outflow constant

# PID parameters (tune these)
Kp = 10
Ki = 0.5
Kd = 0.2

# Setpoint
setpoint = 6.0

# Storage
level = np.zeros(len(time))
control = np.zeros(len(time))
error_integral = 0
prev_error = 0

for i in range(1, len(time)):
    # Error
    error = setpoint - level[i-1]
    
    # PID calculations
    error_integral += error * dt
    derivative = (error - prev_error) / dt
    
    u = Kp*error + Ki*error_integral + Kd*derivative
    
    # Clamp input (optional)
    u = max(0, min(u, 10))
    
    control[i] = u

    # Tank dynamics
    inflow = u
    outflow = outflow_coeff * np.sqrt(max(level[i-1], 0))
    
    dLdt = (inflow - outflow) / A
    level[i] = level[i-1] + dLdt * dt

    prev_error = error

# Plot
plt.figure()

plt.subplot(2,1,1)
plt.plot(time, level, label="Level")
plt.axhline(setpoint, linestyle='--', label="Setpoint")
plt.ylabel("Tank Level")
plt.legend()

plt.subplot(2,1,2)
plt.plot(time, control, label="Control Output")
plt.ylabel("Valve/Input Flow")
plt.xlabel("Time (s)")
plt.legend()

plt.tight_layout()
plt.show()