;; domain_numeric_v10: v9 with an action cost for plan metrics (T4.3). Every wait
;; adds 5 to (total-cost) -- the game seconds it stands for -- and every other
;; action 1, so a problem with (:metric minimize (total-cost)) asks for the plan
;; that reaches the goal soonest, then with the fewest orders. Without a :metric
;; the domain behaves exactly as v9.
(define (domain sc2-terran-macro)
  (:requirements :typing :numeric-fluents)

  (:functions
    (minerals) (vespene) (mining-rate) (gas-rate)
    (supply-used) (supply-cap)
    (depot-count) (barracks-count) (refinery-count)
    (factory-count) (engineeringbay-count) (cc-count)
    (marine-count) (marauder-count) (tank-count)
    (weapon-upgrades) (armor-upgrades)
    (techlab-barracks-count) (techlab-factory-count) (stimpack)
    (attacks-launched)
    (rax-time) (factory-time) (attack-threshold) (total-cost)
)

  (:action wait_for_minerals
  :parameters () :precondition ()
  :effect (and (increase (total-cost) 5) (increase (minerals) (mining-rate))
               (increase (vespene) (gas-rate))
               (increase (rax-time) (* 5 (barracks-count)))
               (increase (factory-time) (* 5 (factory-count)))))

  (:action build_supply_depot
    :parameters ()
    :precondition (and (< (attacks-launched) 1)
        (>= (minerals) 100)
        (<= (supply-cap) 192)
        (< (- (supply-cap) (supply-used)) 16)
    )
    :effect (and (increase (total-cost) 1)
        (decrease (minerals) 100)
        (increase (supply-cap) 8)
        (increase (depot-count) 1) ;
    )
  )

  (:action build_barracks
    :parameters ()
    :precondition (and (< (attacks-launched) 1)
        (>= (minerals) 150)
        (>= (depot-count) 1) ;
        (< (barracks-count) (* 3 (cc-count)))
    )
    :effect (and (increase (total-cost) 1)
        (decrease (minerals) 150)
        (increase (barracks-count) 1)
    )
  )

  (:action build_refinery
  :parameters ()
  :precondition (and (< (attacks-launched) 1) (>= (minerals) 75) (>= (cc-count) 1)
                      (< (refinery-count) (* 2 (cc-count))))
  :effect (and (increase (total-cost) 1) (decrease (minerals) 75)
               (increase (refinery-count) 1)
               (increase (gas-rate) 25)))

(:action wait_for_vespene
  :parameters () :precondition (>= (refinery-count) 1)
  :effect (and (increase (total-cost) 5) (increase (vespene) (gas-rate))
               (increase (minerals) (mining-rate))
               (increase (rax-time) (* 5 (barracks-count)))
               (increase (factory-time) (* 5 (factory-count)))))

  (:action expand
  :parameters ()
  :precondition (and (< (attacks-launched) 1) (>= (minerals) 400) (< (cc-count) 2))
  :effect (and (increase (total-cost) 1) (decrease (minerals) 400)
               (increase (cc-count) 1)
               (increase (mining-rate) 40)))


(:action build_factory
  :parameters ()
  :precondition (and (< (attacks-launched) 1) (>= (minerals) 150) (>= (vespene) 100) (>= (barracks-count) 1)
                      (< (factory-count) (cc-count)))
  :effect (and (increase (total-cost) 1) (decrease (minerals) 150) (decrease (vespene) 100) (increase (factory-count) 1)))

;; Tech Lab add-ons. A Barracks or Factory can carry at most one add-on, so
;; the precondition demands a production building that does not yet have one.
;; Without these the game silently rejects every Marauder and Siege Tank
;; order: the domain would claim a unit was trained that never existed.
(:action build_techlab_barracks
  :parameters ()
  :precondition (and (< (attacks-launched) 1) (>= (minerals) 50) (>= (vespene) 25)
                      (> (barracks-count) (techlab-barracks-count)))
  :effect (and (increase (total-cost) 1) (decrease (minerals) 50) (decrease (vespene) 25)
               (increase (techlab-barracks-count) 1)))

(:action build_techlab_factory
  :parameters ()
  :precondition (and (< (attacks-launched) 1) (>= (minerals) 50) (>= (vespene) 25)
                      (> (factory-count) (techlab-factory-count)))
  :effect (and (increase (total-cost) 1) (decrease (minerals) 50) (decrease (vespene) 25)
               (increase (techlab-factory-count) 1)))

(:action train_marauder
  :parameters ()
  :precondition (and (< (attacks-launched) 1) (>= (barracks-count) 1) (>= (techlab-barracks-count) 1)
                      (>= (minerals) 100) (>= (vespene) 25) (>= (rax-time) 21)
                      (<= (+ (supply-used) 2) (supply-cap)))
  :effect (and (increase (total-cost) 1) (decrease (minerals) 100) (decrease (vespene) 25) (decrease (rax-time) 21)
               (increase (supply-used) 2) (increase (marauder-count) 1)))

(:action train_siegetank
  :parameters ()
  :precondition (and (< (attacks-launched) 1) (>= (factory-count) 1) (>= (techlab-factory-count) 1)
                      (>= (minerals) 150) (>= (vespene) 125) (>= (factory-time) 32)
                      (<= (+ (supply-used) 3) (supply-cap)))
  :effect (and (increase (total-cost) 1) (decrease (minerals) 150) (decrease (vespene) 125) (decrease (factory-time) 32)
               (increase (supply-used) 3) (increase (tank-count) 1)))



(:action build_engineeringbay
  :parameters ()
  :precondition (and (< (attacks-launched) 1) (>= (minerals) 125) (>= (depot-count) 1) (< (engineeringbay-count) 1))
  :effect (and (increase (total-cost) 1) (decrease (minerals) 125) (increase (engineeringbay-count) 1)))

(:action research_weapons
  :parameters ()
  :precondition (and (< (attacks-launched) 1) (>= (engineeringbay-count) 1) (>= (minerals) 100) (>= (vespene) 100)
                      (< (weapon-upgrades) 1))
  :effect (and (increase (total-cost) 1) (decrease (minerals) 100) (decrease (vespene) 100)
               (increase (weapon-upgrades) 1)))

;; Stimpack is researched at a Barracks Tech Lab, so it shares the add-on the
;; Marauders already need. Modelled as a one-shot 0/1 fluent rather than a
;; level counter because the ability does not stack.
(:action research_stimpack
  :parameters ()
  :precondition (and (< (attacks-launched) 1) (>= (techlab-barracks-count) 1) (< (stimpack) 1)
                      (>= (minerals) 100) (>= (vespene) 100))
  :effect (and (increase (total-cost) 1) (decrease (minerals) 100) (decrease (vespene) 100)
               (increase (stimpack) 1)))

  (:action train_marine
    :parameters ()
    :precondition (and (< (attacks-launched) 1)
        (>= (barracks-count) 1)
        (>= (minerals) 50)
        (>= (rax-time) 18)
        (<= (+ (supply-used) 1) (supply-cap))
    )
    :effect (and (increase (total-cost) 1)
        (decrease (minerals) 50)
        (decrease (rax-time) 18)
        (increase (supply-used) 1)
        (increase (marine-count) 1)
    )
  )

  ;; Army value is weighted by unit strength: a Marauder counts as two
  ;; Marines and a Siege Tank as three. Committing the army resets all
  ;; three counters, so the planner must rebuild before attacking again.
  ;;
  ;; The threshold (30 since v8) is the single knob controlling how big a force the
  ;; planner masses before committing it. attacks-launched exists so that
  ;; "commit an attack" is expressible as a goal: the problem generator always
  ;; initialises it to 0, so a goal of (>= (attacks-launched) 1) means "launch
  ;; one more wave", and satisfying it forces the planner to build the army
  ;; first. That is what keeps the attack decision inside the planner.
  (:action attack
  :parameters ()
  :precondition (and (< (attacks-launched) 1)
                     (>= (+ (marine-count) (+ (* 2 (marauder-count)) (* 3 (tank-count)))) (attack-threshold)))
  :effect (and (increase (total-cost) 1) (assign (marine-count) 0) (assign (marauder-count) 0) (assign (tank-count) 0)
               (increase (attacks-launched) 1)))
)
