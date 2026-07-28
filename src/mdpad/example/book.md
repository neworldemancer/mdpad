# Representation Dynamics

An informal, hypothesis-aware account of how learned representations move,
concentrate, and reorganize as information is processed.

## Representation Geometry

A representation assigns to each input $x$ a vector $z = f_\theta(x) \in \mathbb{R}^d$.
The geometry of the induced point cloud — its curvature, intrinsic dimension, and
anisotropy — often carries more signal than any single coordinate.

We treat the empirical covariance $\Sigma = \mathbb{E}[(z-\mu)(z-\mu)^\top]$ as a
first-order probe. Its eigenspectrum $\{\lambda_i\}$ separates directions the model
actively uses from directions it merely tolerates.

## Spectral Modes

Let $L$ be a graph Laplacian built on the representation. Its modes $\phi_k$ with
eigenvalues $0 = \mu_0 \le \mu_1 \le \dots$ give a natural basis for slow, reusable
structure. The claim — still a hypothesis — is that low modes encode geometry that
transfers across tasks, while high modes encode dataset-specific occupancy.

$$ L \phi_k = \mu_k \, \phi_k, \qquad k = 0, 1, 2, \dots $$

## Mode Occupation

Define the occupation of mode $k$ as
$p_k = \langle a, \phi_k\rangle^2 \big/ \sum_j \langle a, \phi_j\rangle^2$,
the fraction of activity a signal $a$ places on that mode. Occupation profiles may
distinguish memorization from generalization, but this connection is presently
proposed, not established.
