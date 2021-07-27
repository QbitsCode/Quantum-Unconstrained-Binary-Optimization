from cycler import cycler
from dwave_qbsolv import QBSolv
from dwave.system.samplers import DWaveSampler
from dwave.system.composites import EmbeddingComposite
import findiff
import matplotlib
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import qde

from plots_general import my_plot, my_scatter

import addcopyfighandler


class Constants:
    a0_per_m = 1.889726124565062e+10
    me_per_amu = 1.822888484770040e+3
    eh_per_cm_1 = 4.556335256391438e-6
    eh_per_ev = 3.6749308136649e-2


class Hydrogen:
    """Hydrogen molecule (H2). All values are in atomic units."""
    equilibrium = 74e-12 * Constants.a0_per_m
    mu = 1.00782503207 * Constants.me_per_amu / 2  # Reduced mass
    freq = 4342 * Constants.eh_per_cm_1
    dissociation_energy = 4.52 * Constants.eh_per_ev
    force = mu * freq ** 2

    @staticmethod
    def get_harmonic_period():
        return np.pi * np.sqrt(2) / Hydrogen.freq

    @staticmethod
    def plot_potential_harmonic(**kwargs):
        equilibrium, force = (Hydrogen.equilibrium, Hydrogen.force)
        grid = np.linspace(-0.2, 0.2, 100) + equilibrium
        pot = force * (grid - equilibrium) ** 2
        axes = my_plot(grid, pot / Constants.eh_per_cm_1, **kwargs)
        axes.set_xlabel(r'$\mathrm{H-H\ dist, a_0}$')
        axes.set_ylabel(r'$\mathrm{Energy, cm^{-1}}$')
        return axes

    @staticmethod
    def harmonic_trajectory(initial_position, initial_speed, t):
        w = Hydrogen.freq
        return Hydrogen.equilibrium + (initial_position - Hydrogen.equilibrium) * np.cos(np.sqrt(2) * w * t) + initial_speed / np.sqrt(2) / w * np.sin(np.sqrt(2) * w * t)

    @staticmethod
    def get_morse_a():
        return np.sqrt(Hydrogen.force / 2 / Hydrogen.dissociation_energy)

    @staticmethod
    def get_potential_morse(r):
        De = Hydrogen.dissociation_energy
        a = Hydrogen.get_morse_a()
        r0 = Hydrogen.equilibrium
        pot = De * (np.exp(-2 * a * (r - r0)) - 2 * np.exp(-a * (r - r0)))
        return pot

    @staticmethod
    def plot_potential_morse(**kwargs):
        grid = np.linspace(-0.7, 9, 1000) + r0
        pot = Hydrogen.get_potential_morse(grid)
        axes = my_plot(grid, pot / Constants.eh_per_cm_1, **kwargs)
        axes.set_xlabel(r'$\mathrm{r, a_0}$')
        axes.set_ylabel(r'$\mathrm{Energy, cm^{-1}}$')
        return axes

    @staticmethod
    def get_force_morse(r):
        re = Hydrogen.equilibrium
        De = Hydrogen.dissociation_energy
        a = Hydrogen.get_morse_a()
        force = 2 * a * De * (np.exp(-2 * a * (r - re)) - np.exp(-a * (r - re)))
        return force

    @staticmethod
    def plot_force_morse(**kwargs):
        grid = np.linspace(-0.7, 9, 1000) + re
        force = Hydrogen.get_force_morse(grid)
        axes = my_plot(grid, force / Constants.eh_per_cm_1, **kwargs)
        axes.set_xlabel(r'$\mathrm{r, a_0}$')
        axes.set_ylabel(r'$\mathrm{Force, cm^{-1} / a_0}$')
        axes.set_ylim(bottom=-20000, top=20000)
        return axes

    @staticmethod
    def morse_trajectory_v0(initial_position, t):
        """Returns morse trajectory at time t with specified initial position and 0 initial speed."""
        De = Hydrogen.dissociation_energy
        mu = Hydrogen.mu
        a = Hydrogen.get_morse_a()
        re = Hydrogen.equilibrium
        r0 = initial_position

        c1 = np.exp(a * re)
        c2 = np.exp(a * r0)
        c3 = -De * c1 / c2 * (2 - c1 / c2)
        c4 = De + c2 * c3 / c1
        tau = np.exp(np.sqrt(2 * c3 / mu, dtype=complex) * a * t)

        trajectory = np.log(c1 ** 2 * tau * (c3 * De + (De - c4 / tau) ** 2) / (2 * c1 * c3 * c4)) / a
        return trajectory


def get_problem(problem, **kwargs):
    """Returns problem-specific values: grid, system_terms, boundary condition and answer.
    kwargs: N, time_max, initial_position."""
    if problem == 0:
        # Problem: dy/dx = exp(x); y(0) = 1
        # Solution: y(x) = exp(x)
        N = kwargs.get('N', 11)
        grid = np.linspace(0, 1, N)
        system_terms = np.empty((1, 3), dtype=object)
        system_terms[0, 0] = lambda x, y: -np.exp(x)
        system_terms[0, 1] = lambda x, y: 0
        system_terms[0, 2] = lambda x, y: 1
        known_points = np.exp(grid[0:1])
        solution = lambda x: np.exp(x)

    elif problem == 1:
        # Problem: r'' + 2 * w^2 * r - 2 * w^2 * re = 0; r(0) = r0; r'(0) = v0
        # Solution: r(t) = re + (r0 - re) * cos(2^0.5 * w * t) + v0 / 2^0.5 / w * sin(2^0.5 * w * t)
        N = kwargs.get('N', 10)
        w = Hydrogen.freq
        period = Hydrogen.get_harmonic_period()
        grid = np.linspace(0, period, N)
        system_terms = np.empty((1, 4), dtype=object)
        system_terms[0, 0] = lambda x, y: -2 * w ** 2 * Hydrogen.equilibrium
        system_terms[0, 1] = lambda x, y: 2 * w ** 2
        system_terms[0, 2] = lambda x, y: 0
        system_terms[0, 3] = lambda x, y: 1
        initial_position = 1.3
        initial_speed = 0
        known_points = np.array([initial_position, initial_position + initial_speed])
        solution = lambda t: Hydrogen.harmonic_trajectory(initial_position, initial_speed, t)

    elif problem == 2:
        # Problem: r'' = 2 * De * a / m * (exp(-2 * a * (r - re)) - exp(-a * (r - re))); r(0) = r0; r'(0) = 0
        # Solution: Hydrogen.morse_trajectory_v0
        time_max = kwargs.get('time_max', 1000)
        N = kwargs.get('N', 1001)
        initial_position = kwargs.get('initial_position', 1.3)
        grid = np.linspace(0, time_max, N)
        known_points = np.array([initial_position, initial_position])[np.newaxis, :]

        De = Hydrogen.dissociation_energy
        a = Hydrogen.get_morse_a()
        m = Hydrogen.mu
        re = Hydrogen.equilibrium

        system_terms = np.empty((1, 4), dtype=object)
        system_terms[0, 0] = lambda t, r: -2 * De * a / m * (np.exp(-2 * a * (r - re)) - np.exp(-a * (r - re)))
        system_terms[0, 1] = lambda t, r: 0
        system_terms[0, 2] = lambda t, r: 0
        system_terms[0, 3] = lambda t, r: 1

        solution = lambda t: Hydrogen.morse_trajectory_v0(initial_position, t)

    elif problem == 21:
        # Problem: r'' = 2 * De * a / m * (exp(-2 * a * (r - re)) - exp(-a * (r - re))); r(0) = r0; r'(0) = 0
        # Solution: Hydrogen.morse_trajectory_v0
        time_max = kwargs.get('time_max', 1000)
        N = kwargs.get('N', 1001)
        initial_position = kwargs.get('initial_position', 1.3)
        grid = np.linspace(0, time_max, N)
        known_points = np.array([initial_position, 0])[:, np.newaxis]

        De = Hydrogen.dissociation_energy
        a = Hydrogen.get_morse_a()
        m = Hydrogen.mu
        re = Hydrogen.equilibrium

        system_terms = np.empty((2, 3), dtype=object)
        system_terms[0, 0] = lambda t, r, p: -p / m
        system_terms[1, 0] = lambda t, r, p: -Hydrogen.get_force_morse(r)
        system_terms[:, 1] = lambda t, r, p: 0
        system_terms[:, 2] = lambda t, r, p: 1

        solution = lambda t: Hydrogen.morse_trajectory_v0(initial_position, t)

    else:
        raise Exception('Unknown problem')

    return grid, system_terms, known_points, solution


def get_analytical_solution(problem=0, N=1000, time_max=300, initial_position=1.3, **kwargs):
    grid, _, _, solution = get_problem(problem, N=N, time_max=time_max, initial_position=initial_position, **kwargs)
    solution_vals = solution(grid)
    if max(abs(np.imag(solution_vals))) < 1e-10:
        solution_vals = np.real(solution_vals)
    return grid, solution_vals


def get_qp_solution(problem, N=100, time_max=300, initial_position=1.3, max_considered_accuracy=1, points_per_step=1, **kwargs):
    """Plots QP solution of a given problem in r-t space."""
    grid, system_terms, solution, _ = get_problem(problem, N=N, time_max=time_max, initial_position=initial_position)
    solution = qde.solve_ode_qp(system_terms, grid, solution, max_considered_accuracy, points_per_step, **kwargs)
    return grid, solution


def get_sampler(sampler_name):
    if sampler_name == 'qbsolv':
        return QBSolv()
    elif sampler_name == 'dwave':
        return EmbeddingComposite(DWaveSampler())
    else:
        raise Exception('Unknown sampler name')


def get_qubo_solution(problem, N=100, time_max=400, initial_position=1.3, bits_integer=6, bits_decimal=15, max_considered_accuracy=1, points_per_step=1, sampler_name='qbsolv', **kwargs):
    grid, system_terms, solution, _ = get_problem(problem, N=N, time_max=time_max, initial_position=initial_position)
    sampler = get_sampler(sampler_name)
    solution = qde.solve_ode_qubo(system_terms, grid, solution, bits_integer, bits_decimal, max_considered_accuracy, points_per_step, sampler, **kwargs)
    return grid, solution


def plot_solution_tr(t, r, **kwargs):
    axes = my_plot(t, r, **kwargs)
    axes.set_xlabel('t, a.u.')
    axes.set_ylabel('r, a.u.')
    return axes


def plot_solution_rp_tr(t, r, **kwargs):
    dt = t[1] - t[0]
    d_dt = findiff.FinDiff(0, dt)
    p = Hydrogen.mu * d_dt(r)
    return plot_solution_rp(r, p, **kwargs)


def plot_solution_rp(r, p, **kwargs):
    axes = my_scatter(r, p, **kwargs)
    axes.set_xlabel('r, a.u.')
    axes.set_ylabel('p, a.u.')
    return axes


def plot_error(solution_n, true_answer_n, Ns=None, **kwargs):
    """Plots error at given values of Ns. solution_n and answer_n are function of n."""
    if Ns is None:
        Ns = np.geomspace(10, 100, 5, dtype=int)
    plot_data = np.empty((2, len(Ns)))
    for i in range(len(Ns)):
        N = Ns[i]
        solution = solution_n(N)
        true_answer = true_answer_n(N)
        error = abs((solution[-1] - true_ans[-1]) / true_ans[-1]) * 100
        plot_data[:, i] = (N, error)

    axes = my_plot(plot_data[0, :], plot_data[1, :], **kwargs)
    axes.set_xlabel('N')
    axes.set_ylabel('Error, %')
    return axes


if __name__ == '__main__':
    np.set_printoptions(precision=15, linewidth=200)
    mpl.rcParams['axes.prop_cycle'] = cycler(color='brgkcmy')

    grid, solution = get_analytical_solution(problem=21, N=1600, time_max=400)
    axes = plot_solution_rp_tr(grid, solution)

    _, solution = get_qubo_solution(problem=21, N=200, time_max=400, sampler_name='qbsolv', num_repeats=100)
    axes = plot_solution_rp(solution[0, :], solution[1, :], axes=axes)

    _, solution = get_qubo_solution(problem=21, N=200, time_max=400, sampler_name='dwave', num_reads=10000)
    axes = plot_solution_rp(solution[0, :], solution[1, :], axes=axes)

    if not mpl.is_interactive():
        plt.show()
