import tensorflow as tf
import numpy as np
from costs.cost import DiscreteCost
# Note(Somil): There is angle_normalize function in angle_utils in utils folder. Let's use that instead? This will take
# out the redundant code.
def angle_normalize(x):
    return (((x + np.pi) % (2 * np.pi)) - np.pi)

class QuadraticRegulatorRef(DiscreteCost):
    """ 
    Creates a quadratic cost of the form 0.5*[x-x_ref(t) u-u_ref(t)]*C*[x-x_ref(t) u-u_ref(t)]^T + 
    c*[x-x_ref(t) u-u_ref(t)]^T for every time step. However, some dimensions are angles, which are wrapped in 
    the cost.
    """
    def __init__(self, trajectory_ref, C, c, system):
        """
        :param: x_ref, u_ref: state and controller reference trajectories
                C, c: Quadratic and linear penalties
                angle_dims: index array which specifies the dimensions of the state that corresponds to angles and 
                should be wrapped.
        """
        # Note(Somil):
        #  1. It would be great to augment C, c with the dimensions.
        #  2. Why are we inputting System to the cost function? Cost function should not be able to access the
        # system directly.
        #  3. There are no x_ref and u_ref inputs to the function as mentioned in params above. Is trajectory_ref a
        # member of the trajectory class or is it a tensor?
        self.system = system
        x_dim, u_dim = system._x_dim, system._u_dim #d,f
        assert (tf.reduce_all(tf.equal(C[:x_dim, x_dim:], tf.transpose(C[x_dim:, :x_dim]))).numpy())
        assert (x_dim + u_dim) == C.shape[0].value == C.shape[1].value == c.shape[0].value
        self._x_dim, self._u_dim = x_dim, u_dim
        self.angle_dims = system._angle_dims
        self.trajectory_ref = trajectory_ref
        n, k, g = trajectory_ref.n, trajectory_ref.k, C.shape[0]
        
        # Note(Somil): Let's use the style guide of PyCharm/CLion. There should be a space after each argument (for
        # example after commas in the next two lines). I know I'm being picky here, but this makes code much more
        # readable, and will reduce our efforts significantly whenever we will publish this code.
        self._C_nkgg = tf.broadcast_to(C, (n,k,g,g))
        self._c_nkg = tf.broadcast_to(c, (n,k,g))
        super().__init__(x_dim=self._x_dim, u_dim=self._u_dim)

        # Note(Somil): I think it is time-varying cost.
        self.isTimevarying = False
        self.isNonquadratic = False
    
    def compute_trajectory_cost(self, trajectory):
        # Note(Somil): Let's make sure that the signature is same between this function and the one defined in the
        # parent class.
        with tf.name_scope('compute_traj_cost'):
            z_nkg = self.construct_z(trajectory)
            C_nkgg, c_nkg = self._C_nkgg, self._c_nkg
            # Note(Somil): Let's adhere to the style guide?
            Cz_nkg = tf.squeeze(tf.matmul(C_nkgg, z_nkg[:,:,:,None]))
            zCz_nk = tf.reduce_sum(z_nkg*Cz_nkg, axis=2)
            cz_nk = tf.reduce_sum(c_nkg*z_nkg, axis=2)
            # Let's add dimensions to the cost variable below. Is is nxk?
            cost = .5*zCz_nk + cz_nk
            return cost, tf.reduce_sum(cost, axis=1)

    def quad_coeffs(self, trajectory, t=None):
        # Return terms H_xx, H_xu, H_uu, J_x, J_u
        with tf.name_scope('quad_coeffs'):
            H_nkgg = self._C_nkgg
            J_nkg = self._c_nkg
            z_nkg = self.construct_z(trajectory)
            # Note(Somil): Style guide.
            Hz_nkg = tf.squeeze(tf.matmul(H_nkgg, z_nkg[:,:,:,None]), axis=-1)
            return H_nkgg[:,:,:self._x_dim, :self._x_dim], \
                   H_nkgg[:,:,:self._x_dim, self._x_dim:], \
                   H_nkgg[:,:,self._x_dim:, self._x_dim:], \
                   J_nkg[:,:,:self._x_dim] + Hz_nkg[:,:,:self._x_dim], \
                   J_nkg[:,:,self._x_dim:] + Hz_nkg[:,:,self._x_dim:]

    def construct_z(self, trajectory):
        """ Input: A trajectory with x_dim =d and u_dim=f
            Output: z_nkg - a tensor of size n,k,g where g=d+f
        """
        with tf.name_scope('construct_z'):
            x_nkd, u_nkf = self.system.parse_trajectory(trajectory)
            x_ref_nkd, u_ref_nkf = self.system.parse_trajectory(self.trajectory_ref)
            delx_nkd = x_nkd - x_ref_nkd 
            delu_nkf = u_nkf - u_ref_nkf
            # Note(Somil): Style guide.
            z_nkg = tf.concat([delx_nkd[:,:,:self.angle_dims],
                              angle_normalize(delx_nkd[:,:,self.angle_dims:self.angle_dims+1]),
                              delx_nkd[:,:,self.angle_dims+1:],
                              delu_nkf], axis=2)
            return z_nkg
