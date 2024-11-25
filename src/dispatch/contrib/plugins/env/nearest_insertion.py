# The code is similar to this example.
# https://github.com/marlonsd/TSPHeuristics/blob/master/constructive_heuristics.py
# No license was included in that code snippet.

# TODO: Split into NI (nearthest_insertion), NN (earest_neighbour), farthest insertion....
class NearestInsertion:
    def __init__(self, locations, travel_router, return_start_distance=False): 
        self.locations = locations
        self.travel_router = travel_router
        self.return_start_distance=return_start_distance
    def get_distance(self, i, j):
        return self.travel_router.get_travel_minutes_2locations(self.locations[i][0:2], self.locations[j][0:2])

    def solve_ni(self):
        points = list(range(len(self.locations)))

        current = points[0]

        points.remove(current)

        i = current
        j = points[0]
        cij = self.get_distance(i,j)
        for point in points:
            if self.get_distance(i, point) < cij:
                cij = self.get_distance(i, point)
                j = point

        points.remove(j) 
        edges = [(i,j)]

        visited = []
        visited.append(i)
        visited.append(j)

        while len(points) > 0:
            i = visited[0]
            k = points[0]
            crj = self.get_distance(k,i)

            for point in points:
                for c in visited:
                    dist = self.get_distance(point,c)
                    if dist < crj:
                        k = point

            i = edges[0][0]
            j = edges[0][1]
            c_min = self.get_distance(i,k) + self.get_distance(k,j) - self.get_distance(i,j)

            for e in edges:
                aux_i = e[0]
                aux_j = e[1]
                dist = self.get_distance(aux_i,k) + self.get_distance(k,aux_j) - self.get_distance(aux_i,aux_j)
                if dist < c_min:
                    c_min = dist
                    i = aux_i
                    j = aux_j

            edges.remove((i,j))
            edges.append((i,k))
            edges.append((k,j))

            visited.append(k)
            points.remove(k)


        cost = 0
        next_node = {}
        points = list(range(1,len(self.locations)))

        for e in edges:
            i = e[0]
            j = e[1]
            next_node[i] = j
            # cost += self.get_distance(i, j)
        n = 0
        solution = [n]
        start_distance = [0]
        while len(points) > 0:
            k=next_node[n]
            points.remove(k)
            solution.append(k)
            start_distance.append(self.get_distance(n,k))
            n=k
        if self.return_start_distance:
            return solution, cost, edges, start_distance
        else:
            return solution, cost, edges



    def solve_weighted_nn(self):
        assert not self.return_start_distance, "not implemented for self.return_start_distance"
        points = list(range(len(self.locations)))

        current = points[0]

        points.remove(current)
        tour = [current]

        while len(points) > 0:

            # TODO, validate and skip next
            next = points[0]
            for p_i, point in enumerate(points):
                if self.locations[point][3] is not None:
                    # print(self.locations[point])
                    if not (set(self.locations[point][3]) < set(tour)) :
                        # its preceding jobs are not dispatched yet... It should wait for next round...
                        continue
                next = point
                break

            for point in points[p_i+1:]:
                if self.locations[point][3] is not None:
                    # print(self.locations[point])
                    if not (set(self.locations[point][3]) < set(tour)) :
                        # its preceding jobs are not dispatched yet... It should wait for next round...
                        continue

                if self.get_distance(current, point)  * self.locations[point][2] < self.get_distance(current, next) * self.locations[next][2]:
                    next = point      
            tour.append(next)
            points.remove(next)
            current = next

        cost = 0 
        for i in range(len(tour)-1):
            cost += self.get_distance(tour[i], tour[i+1])

        cost += self.get_distance(tour[i+1], tour[0])

        return  tour,cost,None


    def solve_nn(self):
        points = list(range(len(self.locations)))

        current = points[0]

        points.remove(current)
        tour = [current]

        while len(points) > 0:
            next = points[0]
            for point in points:
                if self.get_distance(current, point) < self.get_distance(current, next):
                    next = point      
            tour.append(next)
            points.remove(next)
            current = next

        # tour.append(tour[0])

        cost = 0
        # for i in range(len(tour)-1):
        #     cost += self.get_distance(tour[i], tour[i+1])

        # cost += self.get_distance(tour[i+1], tour[0])

        return  tour,cost,None



if __name__ == '__main__':

    from dispatch.plugins.kandbox_planner.travel_time_plugin import HaversineTravelTime
    travel_router = HaversineTravelTime(
        travel_speed=20,
        min_minutes=1,
        max_minutes=180,
        travel_mode="driving",
    )  
    assigned_job_codes = ['1899880821-drop', '1899832977-drop', '1899901404-drop', '1900315053-pick', 
    '1900315053-drop', '1900024326-pick', '1899902448-drop', '1900024326-drop'] 

    locations = [( 114.93272,25.84046, 1, None),
        (114.91077045217772, 25.830600932478298, 1, None),
        (114.88708702867173, 25.841540684932582, 1, None),
        (114.91428242094996, 25.83758364205793, 1, None),
        (114.9412496869159, 25.83052857600292, 0.2, None),
        (114.92459680564009, 25.836471503581322,  1, [4]),
        (114.94294025678998, 25.83002053025335,  0.2, None),
        (114.95152927426479, 25.850868400668713,  1, None),
        (114.97976851173351, 25.863788576335843,  1, [6]),
    ]

    ni  = NearestInsertion(locations=locations, travel_router= travel_router)
    solution_index, c, e = ni.solve_weighted_nn()
    print( [ assigned_job_codes[i-1] for i in solution_index[1:]] )


