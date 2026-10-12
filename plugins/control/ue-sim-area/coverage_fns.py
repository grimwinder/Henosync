from shapely.geometry import Polygon, LineString, MultiPoint
from shapely.ops import triangulate, unary_union, polygonize
import random
import numpy as np
import matplotlib.pyplot as plt
from math import pi




     
  
    
def sequentialInsertion_greedy(ags, env):
   
   agents = []

   for ag in range(1, ags+1):
       if ag == 1:
           agents.append(Agents(ag, env, ang_bounds=[(-np.pi/2) % (2*np.pi) , (np.pi/2) % (2*np.pi)], nag = ags, R=1))
       elif ag == 2:
           agents[ag-2].k_ag += 1
           agents.append(Agents(ag, env, ang_bounds=[(np.pi/2) % (2*np.pi) , (3*np.pi/2) % (2*np.pi)], nag = ags, R=1))
           agents[ag-1].k_ag += 1
           
       else:
           agents[ag-2].k_ag += 1
           agents[ag-2].GreedyInteraction_insertion(1)
           #print(agents[ag-2].k_ag) 
           agents.append(Agents(ag, env, ang_bounds=[agents[ag-2].ang_bounds[1], (agents[ag-2].ang_bounds[1] + (2*np.pi/agents[ag-2].k_ag)) % (2*np.pi)], nag = ags, R=1))
           agents[ag-1].k_ag = agents[ag-2].k_ag
           #print(agents[ag-1].k_ag)
   return agents 
   
def sequentialInsertion(ags, env):
   start_angle = random.uniform(0, 2 * np.pi)
   total_angle = start_angle + 2 * np.pi

   agents = []

   for ag in range(1, ags+1):
       if ag == ags:
          end_angle = total_angle
       else:
         sector_size = np.pi / (2 ** (ag - 1))
         end_angle = start_angle + sector_size
       agents.append(Agents(ag, env, ang_bounds=[start_angle % (2*np.pi) , end_angle % (2*np.pi)], nag = ags, R=1))
       start_angle = end_angle     
     
   return agents  

class NbrAgents:
    def __init__(self, ag_id, eps, nbr_ang_bound = None):
         self.nbr_id = ag_id
         self.nbr_ang_bound = nbr_ang_bound
         self.adv_bin = type('', (), {})()
         self.adv_bin.a = 0
         self.adv_bin.b = 0
         self.interactions = 0
         self.eps = eps
         self.adv_belief = type('', (), {})()
         
    def update_info(self, ang_bound, nbr_ang_bound, env, i1, i2):
         self.interactions += 1
         self.nbr_ang_bound = nbr_ang_bound
         self.i1 = i1
         self.i2 = i2
         if nbr_ang_bound is not None:
           if env == "Circular":
                A_self = 0.5*((ang_bound[1] - ang_bound[0]) % (2*np.pi))
                A_nbr = 0.5*((self.nbr_ang_bound[1] - self.nbr_ang_bound[0]) % (2*np.pi))
           if (self.interactions > self.i1) and (self.interactions - self.i1 <= self.i2) :
              if (abs(A_self-A_nbr)< self.eps):
                  self.adv_bin.a += 1
              else:
                  self.adv_bin.b += 1
                    
              self.adv_belief.a = self.adv_bin.a/(self.interactions - self.i1)
              self.adv_belief.b = self.adv_bin.b/(self.interactions - self.i1)
                      

    
    
    
          
class Agents:
    def __init__(self, ag_id, envi_type, nag, ang_bounds = None, AoR = None, R = None, adv = None, eps = 0.05, i1 = 10, i2 = 50):
        self.id = ag_id
        self.env = envi_type
        self.nag = nag
        self.k_ag = 1
        self.adv = adv
        self.nbr_list = []
        self.eps = eps
        self.i1 = i1
        self.i2 = i2
        
        if self.env == "Circular" or self.env == "RegularPolygons": 
          if ang_bounds == None:
            raise TypeError("Angular bounds must be provided for circular/regular polygonal environments.")
          else:
            self.ang_bounds = ang_bounds
            self.ang_pos = (self.ang_bounds[0] + (self.circ_diff(self.ang_bounds[0], self.ang_bounds[1])/2))%(2*np.pi)
            self.true_bounds = self.ang_bounds    
          if isinstance(R, (int, float)):
            self.R = R 
          else:
            raise TypeError("Radius must be provided for circular/regular polygonal environments and it must be a int/float.")
          
        elif self.env == "RandomPolygon":
          if AoR == None:
            raise TypeError("Area of responsibility must be provided for random polygonal environments.")
          else:
            self.AoR = AoR
    
    
    def adv_AoR_misrepresent(self, nbr_id):
    
         th = self.circ_diff(self.ang_bounds[0], self.ang_bounds[1])
         alp = random.random()
         if (nbr_id == ((self.id% self.nag) + 1)):
                self.ang_bounds = [0, 0]
                self.ang_bounds[0] = (self.true_bounds[1] - alp*th) % (2*np.pi) 
                self.ang_bounds[1] = (self.true_bounds[1]) % (2*np.pi) 
            
         elif (nbr_id == (((self.id - 2) % self.nag) + 1)) :
                self.ang_bounds = [0, 0]
                self.ang_bounds[1] = (self.true_bounds[0] + alp*th) % (2*np.pi) 
                self.ang_bounds[0] = (self.true_bounds[0]) % (2*np.pi) 
         elif (nbr_id > self.id) :
                self.ang_bounds = [0, 0]
                self.ang_bounds[0] = (self.true_bounds[1] - alp*th) % (2*np.pi) 
                self.ang_bounds[1] = (self.true_bounds[1]) % (2*np.pi) 
         elif (nbr_id < self.id) :
                self.ang_bounds = [0, 0]
                self.ang_bounds[1] = (self.true_bounds[0] + alp*th) % (2*np.pi) 
                self.ang_bounds[0] = (self.true_bounds[0]) % (2*np.pi)
         
          
    def key_union_chks(self, bounds1, bounds2, tol):
         bit = False
         union_bounds = [0, 0] 
         if abs(bounds1[0] - bounds2[1])< tol:
              #print("Case 1")
              bit = True 
              union_bounds[0] = bounds2[0]
              union_bounds[1] = bounds1[1]
              
         elif abs(bounds1[1] - bounds2[0])< tol:
              #print("Case 2")
              bit = True
              union_bounds[0] = bounds1[0]
              union_bounds[1] = bounds2[1]
                  
         elif (bounds1[0]<= bounds2[0]) and (bounds1[1]>= bounds2[1]):
              bit = True
              #print("Case 3")
              union_bounds[0] = bounds1[0]
              union_bounds[1] = bounds1[1]
              
         elif (bounds1[0]>= bounds2[0]) and (bounds1[1]<= bounds2[1]):
              bit = True   
              #print("Case 4")
              union_bounds[0] = bounds2[0]
              union_bounds[1] = bounds2[1]
                     
         elif (bounds1[0]< bounds2[0]) and (bounds1[1]< bounds2[1]) and (bounds1[1]> bounds2[0]):
              bit = True   
              #print("Case 5")       
              union_bounds[0] = bounds1[0]
              union_bounds[1] = bounds2[1]
                  
         elif (bounds1[0]> bounds2[0]) and (bounds1[1]> bounds2[1]) and (bounds1[0]< bounds2[1]):
              bit = True   
              #print("Case 6")       
              union_bounds[0] = bounds2[0]
              union_bounds[1] = bounds1[1]
         return bit, union_bounds     
                            
    
    def union_info(self, nbr_AoR, tol = 1e-3):          
          if (self.ang_bounds[1]< self.ang_bounds[0]):
               self.ang_bounds = [[self.ang_bounds[0], 2*np.pi],[0, self.ang_bounds[1]]]
          else:
              self.ang_bounds = [self.ang_bounds]     
          
          if (nbr_AoR[1]< nbr_AoR[0]):
               nbr_AoR = [[nbr_AoR[0], 2*np.pi],[0, nbr_AoR[1]]]
          else:
              nbr_AoR = [nbr_AoR]     
        
          union = []
          
          for cnt_i, i in enumerate(self.ang_bounds):
                for cnt_j, j in enumerate(nbr_AoR):
                    #print("i " + str(i))
                    #print("j " + str(j))
                    
                    bit, bounds = self.key_union_chks(i, j, tol)
                    if bit:
                      union.append(bounds)
                      
                    if (len(self.ang_bounds)==1 and len(nbr_AoR) == 2):
                          if bit:
                             if cnt_j == 0:
                                 union.append(nbr_AoR[1])
                             else:
                                 union.insert(0, nbr_AoR[0])
                                   
                    elif (len(self.ang_bounds)==2 and len(nbr_AoR) == 1):
                          if bit:
                             if cnt_i == 0:
                                 union.append(self.ang_bounds[1])
                             else:
                                 union.insert(0, self.ang_bounds[0])
                                   
                                    
          #print("Union")
          #print(union)
          
          if len(union) == 1:
             #print("Scenario 1")
             return union[0], self.circ_diff(union[0][0], union[0][1]), 1 
          elif len(union) == 2:
             #print("Scenario 2")
             return [union[0][0],union[1][1]], self.circ_diff(union[0][0], union[1][1]), 1
          else:
             self.ang_bounds = self.ang_bounds[0]
             return [0,0], 0, 0  
                
     
    
    def circ_diff(self,a, b):
          diff = (b-a) % (2*np.pi)
          return diff      
   
    def union_info_new(self, bounds1, bounds2, tol = 1e-3):          
          if (bounds1[1]< bounds1[0]):
               bounds1 = [[bounds1[0], 2*np.pi],[0, bounds1[1]]]
          else:
              bounds1 = [bounds1]     
          
          if (bounds2[1]< bounds2[0]):
               bounds2 = [[bounds2[0], 2*np.pi],[0, bounds2[1]]]
          else:
              bounds2 = [bounds2]     
        
          union = []
          
          for cnt_i, i in enumerate(bounds1):
                for cnt_j, j in enumerate(bounds2):
                    #print("i " + str(i))
                    #print("j " + str(j))
                    
                    bit, bounds = self.key_union_chks(i, j, tol)
                    if bit:
                      union.append(bounds)
                      
                    if (len(bounds1)==1 and len(bounds2) == 2):
                          if bit:
                             if cnt_j == 0:
                                 union.append(bounds2[1])
                             else:
                                 union.insert(0, bounds2[0])
                                   
                    elif (len(bounds1)==2 and len(bounds2) == 1):
                          if bit:
                             if cnt_i == 0:
                                 union.append(bounds1[1])
                             else:
                                 union.insert(0, bounds1[0])
                                   
                                    
          #print("Union")
          #print(union)
          
          if len(union) == 1:
             #print("Scenario 1")
             return union[0], self.circ_diff(union[0][0], union[0][1]), 1 
          elif len(union) == 2:
             #print("Scenario 2")
             return [union[0][0],union[1][1]], self.circ_diff(union[0][0], union[1][1]), 1
          else:
             #bounds1 = self.ang_bounds[0]
             return [0,0], 0, 0

    def update_k_ag(self, nbr_k_ag):
         if self.k_ag < nbr_k_ag:
                self.k_ag = nbr_k_ag       
            
    def get_nbrs(self, agents): 
        nbrs = []
        for ag in agents:
          #print(ag.id)
          #print(ag.ang_bounds)
          if ag.id != self.id:
             _, _, bit = self.union_info_new(self.ang_bounds, ag.ang_bounds)
             if bit:
              nbrs.append(ag.id)
        return nbrs   
            
         
    def hybrid_greedy_avg(self, nbr_id, nbr_k_ag, nbr_AoR, nbr_ang_pos, tol = 1e-3): 
            self.update_k_ag(nbr_k_ag)
            
            AoR_arclen = 2*np.pi/self.k_ag
            '''
            temp_ang_bounds = [0, 0]
            temp_ang_bounds[1] = self.ang_bounds[1] 
            temp_ang_bounds[0] = (temp_ang_bounds[1] - AoR_arclen) % (2*np.pi)
             
            
            temp_nbr_ang_bounds = [0, 0]
            temp_nbr_ang_bounds[1] = nbr_AoR[1]
            temp_nbr_ang_bounds[0] = (temp_nbr_ang_bounds[1] - AoR_arclen) % (2*np.pi) 
            '''
            bounds, bound_len, bit = self.union_info_new(self.ang_bounds, nbr_AoR, tol)
            print("Bounds")
            print(bounds) 
            print((self.circ_diff(bounds[0], bounds[1])/2)%(2*np.pi))
            if bound_len <= (4*np.pi/self.k_ag) :
               self.GreedyInteraction(nbr_id, nbr_k_ag, (bounds[0] + (self.circ_diff(bounds[0], bounds[1])/2))%(2*np.pi))
               hyb_bit = 0
               
            else:
               self.BilateralInteraction(nbr_id, nbr_AoR) 
               hyb_bit = 1   
            
            
            return hyb_bit  
             
            
    
    def GreedyInteraction(self, nbr_id, nbr_k_ag, ref):
            self.update_k_ag(nbr_k_ag)
           
                
            AoR_arclen = 2*np.pi/self.k_ag
            if (nbr_id == ((self.id% self.nag) + 1)):
                self.ang_bounds = [0, 0]
                self.ang_bounds[1] = (ref) % (2*np.pi) 
                self.ang_bounds[0] = (ref - AoR_arclen) % (2*np.pi) 
            
            elif (nbr_id == (((self.id - 2) % self.nag) + 1)) :
                self.ang_bounds = [0, 0]
                self.ang_bounds[0] = (ref) % (2*np.pi) 
                self.ang_bounds[1] = (ref + AoR_arclen) % (2*np.pi)
            elif (nbr_id > self.id) :
                self.ang_bounds = [0, 0]
                self.ang_bounds[1] = (ref) % (2*np.pi) 
                self.ang_bounds[0] = (ref - AoR_arclen) % (2*np.pi) 
            
            elif (nbr_id < self.id) :
                self.ang_bounds = [0, 0]
                self.ang_bounds[0] = (ref) % (2*np.pi) 
                self.ang_bounds[1] = (ref + AoR_arclen) % (2*np.pi)     
             
            
            #self.ang_bounds[0] = (ref - (AoR_arclen/2)) % (2*np.pi) 
            #self.ang_bounds[1] = (ref + (AoR_arclen/2)) % (2*np.pi) 
            
            self.ang_pos = (self.ang_bounds[0] + (self.circ_diff(self.ang_bounds[0], self.ang_bounds[1])/2))%(2*np.pi)
           
            
            
    def GreedyInteraction_insertion(self, nbr_k_ag):
            self.update_k_ag(nbr_k_ag)
                
            AoR_arclen = 2*np.pi/self.k_ag
            
            self.ang_bounds[1] = self.ang_pos
            self.ang_bounds[0] = (self.ang_bounds[1] - AoR_arclen) % (2*np.pi) 
            self.ang_pos = (self.ang_bounds[0] + (self.circ_diff(self.ang_bounds[0], self.ang_bounds[1])/2))%(2*np.pi)  
            
             
              
     
    def BilateralInteraction(self, nbr_id, nbr_AoR):
        if self.env not in ("Circular", "RegularPolygons"):
            raise ValueError(
                f"BilateralInteraction: unsupported env '{self.env}'. "
                "Expected 'Circular' or 'RegularPolygons'."
            )
        if any(nbr_ag.nbr_id == nbr_id for nbr_ag in self.nbr_list):
              nbr_ag = [obj for obj in self.nbr_list if obj.nbr_id == nbr_id][0]
              nbr_ag.update_info(self.ang_bounds, nbr_AoR, self.env, self.i1, self.i2)    
        else:
              self.nbr_list.append(NbrAgents(nbr_id, self.eps, nbr_ang_bound = nbr_AoR))
              
        bounds, bound_len, bit = self.union_info(nbr_AoR)   
        '''
        print("Bounds")
        print(bounds)
        print("Bounds Length")
        print(bound_len) 
        '''
        if bit:
          if nbr_id == ((self.id% self.nag) + 1) :
            self.ang_bounds = [0, 0]
            #print("update 1")
            self.ang_bounds[0] = bounds[0] 
            self.ang_bounds[1] = (self.ang_bounds[0] + (bound_len/2)) % (2*np.pi)   
          elif nbr_id == (((self.id - 2) % self.nag) + 1):
            #print("update 2")
            self.ang_bounds = [0, 0]
            self.ang_bounds[1] = bounds[1] 
            self.ang_bounds[0] = (self.ang_bounds[1] - (bound_len/2)) % (2*np.pi)
          elif (nbr_id > self.id) :
            self.ang_bounds = [0, 0]
            #print("update 1")
            self.ang_bounds[0] = bounds[0] 
            self.ang_bounds[1] = (self.ang_bounds[0] + (bound_len/2)) % (2*np.pi)   
          elif (nbr_id < self.id)  :
            #print("update 2")
            self.ang_bounds = [0, 0]
            self.ang_bounds[1] = bounds[1] 
            self.ang_bounds[0] = (self.ang_bounds[1] - (bound_len/2)) % (2*np.pi)     
            
          self.ang_pos = (self.ang_bounds[0] + (self.circ_diff(self.ang_bounds[0], self.ang_bounds[1])/2))%(2*np.pi)
        else:
           pass 
            
        if self.adv:
            bounds, _, _ = self.union_info_new(self.ang_bounds, self.true_bounds)
        
            self.true_bounds = bounds   
            self.ang_pos = (self.true_bounds[0] + (self.circ_diff(self.true_bounds[0], self.true_bounds[1])/2))%(2*np.pi) 
        
            
            
def total_sector_union_area(agents):
    """
    Compute the total covered area on a unit circle by angular sectors,
    accounting for overlaps only once.

    Each agent must have:
        agent.ang_bounds = [theta1, theta2]

    Angles are in radians.

    Returns
    -------
    float
        Total union area of all sectors inside the unit circle.
    """

    import numpy as np

    TWO_PI = 2 * np.pi

    intervals = []

    # ------------------------------------------------------------
    # Convert all sectors into non-wrapping angular intervals
    # ------------------------------------------------------------
    for agent in agents:

        th1, th2 = agent.ang_bounds

        th1 = th1 % TWO_PI
        th2 = th2 % TWO_PI

        # Full-circle sector
        if np.isclose((th2 - th1) % TWO_PI, 0):
            return np.pi

        # Wrap-around sector
        if th2 <= th1:

            intervals.append((th1, TWO_PI))
            intervals.append((0.0, th2))

        else:

            intervals.append((th1, th2))

    # ------------------------------------------------------------
    # Sort intervals
    # ------------------------------------------------------------
    intervals.sort(key=lambda x: x[0])

    # ------------------------------------------------------------
    # Merge overlapping intervals
    # ------------------------------------------------------------
    merged = []

    cur_start, cur_end = intervals[0]

    for start, end in intervals[1:]:

        if start <= cur_end:

            cur_end = max(cur_end, end)

        else:

            merged.append((cur_start, cur_end))
            cur_start, cur_end = start, end

    merged.append((cur_start, cur_end))

    # ------------------------------------------------------------
    # Total angular coverage
    # ------------------------------------------------------------
    total_angle = sum(end - start for start, end in merged)

    # ------------------------------------------------------------
    # Sector area in unit circle:
    # A = (1/2) * theta
    # ------------------------------------------------------------
    total_area = 0.5 * total_angle

    return total_area 
 


def plot_area_bounds(max_areas, min_areas, A_des):
    
    n_inter, n_sim = max_areas.shape

    # MATLAB-like color set
    cmap = plt.cm.viridis
    cols = [cmap(i / n_sim) for i in range(n_sim)]

    fig, ax = plt.subplots()

    for i in range(n_sim):

        # Max area (solid line)
        ax.plot(max_areas[:, i],
                color=cols[i],
                linewidth=1.5)

        # Min area (dashed line)
        ax.plot(min_areas[:, i],
                color=cols[i],
                linestyle='--',
                linewidth=1.5)

    ax.set_ylabel("Area", fontsize=14)
    ax.set_xlabel("Interactions", fontsize=14)

    # Reference line (MATLAB yline equivalent)
    h = ax.axhline(A_des,
                   linestyle='--',
                   color='k',
                   linewidth=2)

    ax.legend([h], [f"A_des = {A_des}"])

    ax.grid(True, alpha=0.3)

    plt.show()
    return fig, ax
           

def plot_agent_sectors_wap(
    agents,
    env="Circular",
    sides=6,
    f=1,
    alp=1,
    xlab="N/A",
    xf=16,
    ylab="N/A",
    yf=16,
    axisfs=16,
    num_points=200,
):
    """
    Plot agent sectors on a circular or regular-polygon boundary.

    Parameters
    ----------
    agents    : list of objects, each with:
                - `.ang_bounds` attribute -> (th1, th2) in radians
                - `.ang_pos` attribute    -> midpoint angle in radians
    env       : 'Circular' or 'RegularPolygons'
    sides     : number of polygon sides (only used when env='RegularPolygons')
    f         : colour brightness scale factor; must satisfy 0 < f <= 1
    alp       : fill alpha; must satisfy 0 <= alp <= 1
    xlab/ylab : axis labels
    xf/yf     : axis label font sizes
    axisfs    : tick label font size
    num_points: points used to approximate each arc (default 200)

    Returns
    -------
    fig, ax : the matplotlib Figure and Axes objects
    """

    import numpy as np
    import matplotlib.pyplot as plt

    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------
    if env not in ("Circular", "RegularPolygons"):
        raise ValueError("env must be 'Circular' or 'RegularPolygons'")

    if not (0 < f <= 1):
        raise ValueError("f must be in the range (0, 1]")

    if not (0 <= alp <= 1):
        raise ValueError("alp must be in the range [0, 1]")

    if not agents:
        raise ValueError("agents list is empty")

    TWO_PI = 2 * np.pi
    sector_angle = TWO_PI / sides

    n = len(agents)

    # ------------------------------------------------------------------
    # Colours
    # ------------------------------------------------------------------
    cmap = plt.cm.hsv

    cols = cmap(np.linspace(0, 1, n, endpoint=False))[:, :3]

    cols = [
        (
            min(f * r, 1.0),
            min(f * g, 1.0),
            min(f * b, 1.0),
        )
        for r, g, b in cols
    ]

    # ------------------------------------------------------------------
    # Figure setup
    # ------------------------------------------------------------------
    fig, ax = plt.subplots()

    ax.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)

    ax.set_xlabel(xlab, fontsize=xf)
    ax.set_ylabel(ylab, fontsize=yf)

    ax.tick_params(axis="both", labelsize=axisfs)

    # ------------------------------------------------------------------
    # Plot sectors
    # ------------------------------------------------------------------
    for i, agent in enumerate(agents):

        if agent.adv == True:
          th1, th2 = agent.true_bounds
        else:
          th1, th2 = agent.ang_bounds

        # Normalise angles
        th1 = th1 % TWO_PI
        th2 = th2 % TWO_PI

        # Skip zero-width sectors
        if np.isclose(th1, th2 % TWO_PI):
            print(f"Warning: agent {i} has a zero-width sector — skipped.")
            continue

        # Handle wrap-around
        if th2 <= th1:
            th2 += TWO_PI

        th = np.linspace(th1, th2, num_points)

        # ------------------------------------------------------------------
        # Boundary radius
        # ------------------------------------------------------------------
        if env == "Circular":

            r = np.ones_like(th)

        elif env == "RegularPolygons":

            local_theta = (
                (th + sector_angle / 2)
                % sector_angle
                - sector_angle / 2
            )

            corner_limit = np.pi / sides

            local_theta = np.clip(
                local_theta,
                -corner_limit + 1e-9,
                corner_limit - 1e-9,
            )

            r = np.cos(np.pi / sides) / np.cos(local_theta)

        # ------------------------------------------------------------------
        # Arc coordinates
        # ------------------------------------------------------------------
        x_arc = r * np.cos(th)
        y_arc = r * np.sin(th)

        x = np.concatenate(([0], x_arc))
        y = np.concatenate(([0], y_arc))

        # ------------------------------------------------------------------
        # Fill sector
        # ------------------------------------------------------------------
        if agent.adv == True:
            ax.fill( x, y, color=cols[i], alpha=alp, edgecolor="r", linewidth=1.0,
    linestyle="--")
        else:
         
           ax.fill(x, y, color=cols[i], alpha=alp, edgecolor="k", linewidth=1.0)

        # ------------------------------------------------------------------
        # Agent midpoint from ang_pos
        # ------------------------------------------------------------------
        mid = agent.ang_pos % TWO_PI

        if env == "Circular":

            r_mid = 1.0

        else:

            local_mid = (
                (mid + sector_angle / 2)
                % sector_angle
                - sector_angle / 2
            )

            corner_limit = np.pi / sides

            local_mid = np.clip(
                local_mid,
                -corner_limit + 1e-9,
                corner_limit - 1e-9,
            )

            r_mid = (
                np.cos(np.pi / sides)
                / np.cos(local_mid)
            )

        # ------------------------------------------------------------------
        # Midpoint coordinates
        # ------------------------------------------------------------------
        x_mid = r_mid * np.cos(mid)
        y_mid = r_mid * np.sin(mid)

        # Dot at midpoint
        ax.plot(
            x_mid,
            y_mid,
            marker="o",
            markersize=6,
            color="k",
        )
        
        ax.text(x_mid + 0.03, y_mid + 0.03, str(agent.k_ag), fontsize=10, color="k", ha="left", va="bottom" )

        # ------------------------------------------------------------------
        # Agent label
        # ------------------------------------------------------------------
        label_r = 0.6 * r_mid

        ax.text(
            label_r * np.cos(mid),
            label_r * np.sin(mid),
            agent.id,
            ha="center",
            va="center",
            fontsize=12,
            color="k",
        )

    # ------------------------------------------------------------------
    # Axis formatting
    # ------------------------------------------------------------------
    ax.set_aspect("equal")

    lim = 1.2

    ax.set_xlim([-lim, lim])
    ax.set_ylim([-lim, lim])
    plt.show()
    return fig, ax

def plot_agent_sectors(
    agents,
    env="Circular",
    sides=6,
    f=1,
    alp=1,
    xlab="N/A",
    xf=16,
    ylab="N/A",
    yf=16,
    axisfs=16,
    num_points=200,
):
    """
    Plot agent sectors on a circular or regular-polygon boundary.

    Parameters
    ----------
    agents    : list of objects, each with an `.ang_bounds` attribute (th1, th2) in radians
    env       : 'Circular' or 'RegularPolygons'
    sides     : number of polygon sides (only used when env='RegularPolygons')
    f         : colour brightness scale factor; must satisfy 0 < f <= 1
    alp       : fill alpha; must satisfy 0 <= alp <= 1
    xlab/ylab : axis labels
    xf/yf     : axis label font sizes
    axisfs    : tick label font size
    num_points: points used to approximate each arc (default 200)

    Returns
    -------
    fig, ax : the matplotlib Figure and Axes objects
    """
    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------
    if env not in ("Circular", "RegularPolygons"):
        raise ValueError("env must be 'Circular' or 'RegularPolygons'")
    if not (0 < f <= 1):
        raise ValueError("f must be in the range (0, 1] to keep RGB values valid")
    if not (0 <= alp <= 1):
        raise ValueError("alp (alpha) must be in the range [0, 1]")
    if not agents:
        raise ValueError("agents list is empty — nothing to plot")

    TWO_PI = 2 * np.pi

    # FIX #2: define sector_angle unconditionally so it is always in scope
    sector_angle = TWO_PI / sides

    n = len(agents)
    
    # ------------------------------------------------------------------
    # Colours
    # FIX #1: clamp each channel to [0, 1] after scaling by f
    # ------------------------------------------------------------------
    cmap = plt.cm.hsv
    cols = cmap(np.linspace(0, 1, n, endpoint=False))[:, :3]
    cols = [
        (min(f * r, 1.0), min(f * g, 1.0), min(f * b, 1.0))
        for r, g, b in cols
    ]
   
    # ------------------------------------------------------------------
    # Figure setup
    # ------------------------------------------------------------------
    fig, ax = plt.subplots()
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)
    ax.set_xlabel(xlab, fontsize=xf)
    ax.set_ylabel(ylab, fontsize=yf)
    ax.tick_params(axis="both", labelsize=axisfs)

    # ------------------------------------------------------------------
    # Regular polygon boundary
    # ------------------------------------------------------------------
    
    # ------------------------------------------------------------------
    # Plot sectors
    # ------------------------------------------------------------------
    for i, agent in enumerate(agents):
        th1, th2 = agent.ang_bounds

        # Normalise angles to [0, 2π)
        th1 = th1 % TWO_PI
        th2 = th2 % TWO_PI

        # FIX #4: guard against zero-width sectors
        if np.isclose(th1, th2 % TWO_PI):
            print(f"Warning: agent {i} has a zero-width sector — skipped.")
            continue

        # Handle wrap-around
        if th2 <= th1:
            th2 += TWO_PI

        th = np.linspace(th1, th2, num_points)

        # ------------------------------------------------------------------
        # Compute boundary radius along each angle
        # ------------------------------------------------------------------
        if env == "Circular":
            r = np.ones_like(th)

        elif env == "RegularPolygons":
            # FIX #5: local_theta is clipped slightly inside ±π/sides to
            #         prevent r from diverging when the arc crosses a vertex
            local_theta = (th + sector_angle / 2) % sector_angle - sector_angle / 2
            corner_limit = np.pi / sides
            local_theta = np.clip(local_theta, -corner_limit + 1e-9, corner_limit - 1e-9)
            r = np.cos(np.pi / sides) / np.cos(local_theta)

        x_arc = r * np.cos(th)
        y_arc = r * np.sin(th)

        x = np.concatenate(([0], x_arc))
        y = np.concatenate(([0], y_arc))

        ax.fill(x, y, color=cols[i], alpha=alp, edgecolor="k", linewidth=1.0)

        # ------------------------------------------------------------------
        # Sector label
        # FIX #3: normalise mid back into [0, 2π) after computing it
        # ------------------------------------------------------------------
        mid = (0.5 * (th1 + th2)) % TWO_PI

        if env == "Circular":
            r_mid = 0.6
        else:
            local_mid = (mid + sector_angle / 2) % sector_angle - sector_angle / 2
            corner_limit = np.pi / sides
            local_mid = np.clip(local_mid, -corner_limit + 1e-9, corner_limit - 1e-9)
            r_mid = 0.6 * (np.cos(np.pi / sides) / np.cos(local_mid))

        ax.text(
            r_mid * np.cos(mid),
            r_mid * np.sin(mid),
            str(i),
            ha="center",
            va="center",
            fontsize=12,
            color="k",
        )

    ax.set_aspect("equal")
    lim = 1.2
    ax.set_xlim([-lim, lim])
    ax.set_ylim([-lim, lim])

    # FIX #7: return fig and ax instead of calling plt.show() internally,
    #         so the caller can save, modify, or display as needed
    plt.show()
    return fig, ax
          
def random_convex_polygon(n_points=20, scale=10):
    # Generate random points
    pts = [(random.uniform(0, scale), random.uniform(0, scale)) for _ in range(n_points)]
    
    # Create convex hull
    hull = MultiPoint(pts).convex_hull
    
    # Extract vertices (remove duplicate last point)
    vertices = list(hull.exterior.coords)[:-1]
    
    return hull, vertices


def random_color():
    return (random.random(), random.random(), random.random())


class GeneralPolygonPartitioning:
    def __init__(self, poly, eps, itr):
        self.poly = poly
        self.eps = eps
        self.itr = itr
        



def iterative_triangulation(poly, itr):
     tris = triangulate(poly)

     # Filter: only keep triangles fully within polygon
     tris = [t for t in tris if t.within(poly)]
     for i in range(itr):
        tris = subdivide_triangles(tris)
      
     return poly, tris 
     
     


def subdivide_triangles(tris):

    subdivided_tris = []

    for t in tris:
         coords = list(t.exterior.coords)[:-1]  # 3 vertices
         A, B, C = coords

         centroid = t.centroid
         G = (centroid.x, centroid.y)

         # Create 3 sub-triangles
         t1 = Polygon([A, B, G])
         t2 = Polygon([B, C, G])
         t3 = Polygon([C, A, G])

         subdivided_tris.extend([t1, t2, t3])
         
         
    return subdivided_tris    




def convex_hull_from_triangles(tris):
    # Combine all triangles into one geometry
    merged = unary_union(tris)
    
    # Get all edges as LineStrings
    lines = merged.boundary

    # Polygonize the edges to get polygons
    polygons = list(polygonize(lines))

    
    merged = max(polygons, key=lambda p: p.area)
    
    return merged 
    
    


def share_edge(tri1, tri2):
   
    coords1 = list(tri1.exterior.coords)[:-1]
    coords2 = list(tri2.exterior.coords)[:-1]
    
    edges1 = [LineString([coords1[i], coords1[(i+1)%3]]) for i in range(3)]
    edges2 = [LineString([coords2[i], coords2[(i+1)%3]]) for i in range(3)]
    
    # Check if any edge is identical
    for e1 in edges1:
        for e2 in edges2:
            if e1.equals(e2) or e1.equals(e2.reverse()):  # reversed edge
                return True
    return False



def aggregate_triangles(tris, target_area, eps=1e-6):
    if not tris:
        return [], None, None

    remaining_tris = tris.copy()
    selected_tris = [remaining_tris.pop(0)]

    queue = selected_tris.copy()

    # Initial union
    merged = unary_union(selected_tris)
    boundary_poly = merged if merged.geom_type == 'Polygon' else max(merged.geoms, key=lambda p: p.area)
    area = boundary_poly.area

    while queue and remaining_tris:
        current = queue.pop(0)

        i = 0
        while i < len(remaining_tris):
            t = remaining_tris[i]

            if share_edge(t, current):

                # --- Candidate selected region ---
                temp_selected = selected_tris + [t]
                merged_temp = unary_union(temp_selected)

                if merged_temp.geom_type != 'Polygon':
                    i += 1
                    continue

                area_temp = merged_temp.area

                # --- Candidate remaining region ---
                temp_remaining = remaining_tris[:i] + remaining_tris[i+1:]
                if temp_remaining:
                    merged_remaining = unary_union(temp_remaining)

                    # 🔴 STRICT CONDITION: must remain a single polygon
                    if merged_remaining.geom_type != 'Polygon':
                        i += 1
                        continue
                else:
                    merged_remaining = None

                # --- Area constraint ---
                if area_temp <= target_area + eps:
                    selected_tris.append(t)
                    queue.append(t)
                    remaining_tris.pop(i)

                    boundary_poly = merged_temp
                    area = area_temp

                    # ✅ Stop condition
                    if target_area - eps <= area <= target_area + eps:
                        remaining_boundary_poly = merged_remaining
                        return selected_tris, boundary_poly, remaining_boundary_poly

                    continue  # don't increment i

            i += 1

    # Final remaining polygon
    if remaining_tris:
        merged_remaining = unary_union(remaining_tris)
        if merged_remaining.geom_type == 'Polygon':
            remaining_boundary_poly = merged_remaining
        else:
            remaining_boundary_poly = None  # failed strict condition
    else:
        remaining_boundary_poly = None

    return selected_tris, boundary_poly, remaining_boundary_poly    
   

def union_boundary_polygon(poly1: Polygon, poly2: Polygon):
    # Merge the two polygons
    merged = unary_union([poly1, poly2])
    
    # Get exact boundary polygon
    # polygonize converts merged boundary lines into polygons
    if merged.geom_type == 'Polygon':
        return merged
    elif merged.geom_type == 'MultiPolygon':
        # Take the polygon with the largest area as outer boundary
        return max(polygonize(merged.boundary), key=lambda p: p.area)
    else:
        raise ValueError(f"Unexpected geometry type: {merged.geom_type}")   