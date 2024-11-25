
# https://www.researchgate.net/publication/272351873_NumPy_SciPy_Recipes_for_Data_Science_k-Medoids_Clustering
# This function is from code snippet Listing 1: k-medoids clustering

import numpy as np
import numpy.random as rnd

def k_medoids_fit(D, k, init_medoids = None, tmax=100):
    # determine dimensions of distance matrix D
    m, n = D.shape

    if init_medoids is None:
        # randomly initialize an array of k medoid indices
        # BUG 1: This might create duplicated nodes 2023-05-21 09:09:26
        M = np.sort(np.random.choice(n, k))
    else:
        M = init_medoids
    # create a copy of the array of medoid indices
    M_new = np.copy(M)

    # initialize a dictionary to represent clusters
    C = {}

    for t in range(tmax):
        # determine clusters, i.e. arrays of data indices
        J = np.argmin(D[:,M], axis=1)
        for kappa in range(k):
            C[kappa] = np.where(J==kappa)[0]

        # update cluster medoids
        for kappa in range(k):
            J = np.mean(D[np.ix_(C[kappa],C[kappa])],axis=1)
            j = np.argmin(J)
            M_new[kappa] = C[kappa][j]
        np.sort(M_new)

        # check for convergence
        if np.array_equal(M, M_new):
            print(f"converged at {t} loops")
            break

        M = np.copy(M_new)
    else:
        # final update of cluster memberships
        J = np.argmin(D[:,M], axis=1)
        for kappa in range(k):
            C[kappa] = np.where(J==kappa)[0]

    # return results
    return M, C


def test_scikit_k_medoids(D, k,  tmax=100):
    # https://scikit-learn-extra.readthedocs.io/en/stable/generated/sklearn_extra.cluster.KMedoids.html
    from sklearn_extra.cluster import KMedoids
    kmedoids = KMedoids(n_clusters=k, random_state=0,max_iter=32).fit(D)
    print(kmedoids.labels_)
    print(kmedoids.cluster_centers_)
    print(kmedoids.predict([[1.1,2.05], [4.21,5.32]]))

if __name__ == "__main__":
    
    from scipy.spatial import distance_matrix

    X = np.asarray([[1, 2], [1, 4], [1, 0],
                    [4, 5], [4, 4], [4, 3],
                    [4.1, 3.5], [4.2, 4.8], [4.2, 5.3],
                    [1, 1.1], [1.5, 2.1], [1, 1.3]])
    test_scikit_k_medoids(X, k=10)
    exit(0)


    D = distance_matrix(X, X)
    M, C = k_medoids_fit(D=D, k=10)
    print(M, C)

    # # https://github.com/kno10/python-kmedoids
    # # Though this looks a good library, but it is GPL

    # import kmedoids
    # km = kmedoids.KMedoids(2, method='fasterpam')
    # c = km.fit(D)
    # print("Loss is:", c.inertia_)
    # print(c)