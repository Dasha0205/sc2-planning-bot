;; domain_temporal: domain_numeric_v11 in PDDL+ (T4.4), for the offline comparison
;; only (experiments/planners_offline.py). The clock actions wait_for_minerals /
;; wait_for_vespene are replaced by one process that runs all the time: mining
;; and production time grow continuously (#t in seconds; mining-rate and gas-rate
;; are per 5 s, as the problem generator writes them). ENHSP plans it with a
;; decision step -dp (1 s); the plan's makespan is its game time.
;; domain_numeric_v11: v9 with room to spend the bank (T4.6, T4.8). Plans now
;; spend the mineral bank down to the floor instead of 1 500 of it a plan, and
;; with v9's limits (Barracks <= 3 per CC, at most 2 CC) there was nothing left
;; to spend it on but waiting for production time: a bank of 4 625 on one CC
;; became a 164-action plan with 76 waits, the army at home for ~6 minutes.
;; Barracks <= 4 per CC and a third CC let the planner turn a floating bank into
;; production and income, which the next plan turns into army.
;; domain_numeric_v9: v8 with the attack threshold as a fluent (T8.3). Since
;; committed units leave the planner's view while they keep their supply, a
;; fixed threshold of 30 becomes unreachable once the army in the field holds
;; more than 170 supply; the problem now sets (attack-threshold) to 30, capped
;; by what can still stand at home (dynamic_problem.attack_threshold).
;; domain_numeric_v8: v7 with a committed attack (T8.3). Against Medium the
;; army was traded away piecemeal: plans attacked first with whatever existed,
;; spent the bank, then attacked again (runs/T8.1_medium, runs/T8.2_v7_medium).
;; Now an attack needs army value 30 (was 20), and it ends the plan: once
;; attacks-launched is 1 nothing more is built or trained, so the bank is spent
;; on the army before it moves out, and one plan holds one attack.
(define (domain sc2-terran-macro)
  (:requirements :typing :numeric-fluents :time)

  (:functions
    (minerals) (vespene) (mining-rate) (gas-rate)
    (supply-used) (supply-cap)
    (depot-count) (barracks-count) (refinery-count)
    (factory-count) (engineeringbay-count) (cc-count)
    (marine-count) (marauder-count) (tank-count)
    (weapon-upgrades) (armor-upgrades)
    (techlab-barracks-count) (techlab-factory-count) (stimpack)
    (attacks-launched)
    (rax-time) (factory-time) (attack-threshold)
)

  (:process harvest
  :parameters () :precondition (>= (mining-rate) 0)
  :effect (and (increase (minerals) (* #t (/ (mining-rate) 5)))
               (increase (vespene) (* #t (/ (gas-rate) 5)))
               (increase (rax-time) (* #t (barracks-count)))
               (increase (factory-time) (* #t (factory-count)))))

  (:action build_supply_depot
    :parameters ()
    :precondition (and (< (attacks-launched) 1)
        (>= (minerals) 100)
        (<= (supply-cap) 192)
        (< (- (supply-cap) (supply-used)) 16)
    )
    :effect (and
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
        (< (barracks-count) (* 4 (cc-count)))
    )
    :effect (and
        (decrease (minerals) 150)
        (increase (barracks-count) 1)
    )
  )

  (:action build_refinery
  :parameters ()
  :precondition (and (< (attacks-launched) 1) (>= (minerals) 75) (>= (cc-count) 1)
                      (< (refinery-count) (* 2 (cc-count))))
  :effect (and (decrease (minerals) 75)
               (increase (refinery-count) 1)
               (increase (gas-rate) 25)))

  (:action expand
  :parameters ()
  :precondition (and (< (attacks-launched) 1) (>= (minerals) 400) (< (cc-count) 3))
  :effect (and (decrease (minerals) 400)
               (increase (cc-count) 1)
               (increase (mining-rate) 40)))


(:action build_factory
  :parameters ()
  :precondition (and (< (attacks-launched) 1) (>= (minerals) 150) (>= (vespene) 100) (>= (barracks-count) 1)
                      (< (factory-count) (cc-count)))
  :effect (and (decrease (minerals) 150) (decrease (vespene) 100) (increase (factory-count) 1)))

;; Tech Lab add-ons. A Barracks or Factory can carry at most one add-on, so
;; the precondition demands a production building that does not yet have one.
;; Without these the game silently rejects every Marauder and Siege Tank
;; order: the domain would claim a unit was trained that never existed.
(:action build_techlab_barracks
  :parameters ()
  :precondition (and (< (attacks-launched) 1) (>= (minerals) 50) (>= (vespene) 25)
                      (> (barracks-count) (techlab-barracks-count)))
  :effect (and (decrease (minerals) 50) (decrease (vespene) 25)
               (increase (techlab-barracks-count) 1)))

(:action build_techlab_factory
  :parameters ()
  :precondition (and (< (attacks-launched) 1) (>= (minerals) 50) (>= (vespene) 25)
                      (> (factory-count) (techlab-factory-count)))
  :effect (and (decrease (minerals) 50) (decrease (vespene) 25)
               (increase (techlab-factory-count) 1)))

(:action train_marauder
  :parameters ()
  :precondition (and (< (attacks-launched) 1) (>= (barracks-count) 1) (>= (techlab-barracks-count) 1)
                      (>= (minerals) 100) (>= (vespene) 25) (>= (rax-time) 21)
                      (<= (+ (supply-used) 2) (supply-cap)))
  :effect (and (decrease (minerals) 100) (decrease (vespene) 25) (decrease (rax-time) 21)
               (increase (supply-used) 2) (increase (marauder-count) 1)))

(:action train_siegetank
  :parameters ()
  :precondition (and (< (attacks-launched) 1) (>= (factory-count) 1) (>= (techlab-factory-count) 1)
                      (>= (minerals) 150) (>= (vespene) 125) (>= (factory-time) 32)
                      (<= (+ (supply-used) 3) (supply-cap)))
  :effect (and (decrease (minerals) 150) (decrease (vespene) 125) (decrease (factory-time) 32)
               (increase (supply-used) 3) (increase (tank-count) 1)))



(:action build_engineeringbay
  :parameters ()
  :precondition (and (< (attacks-launched) 1) (>= (minerals) 125) (>= (depot-count) 1) (< (engineeringbay-count) 1))
  :effect (and (decrease (minerals) 125) (increase (engineeringbay-count) 1)))

(:action research_weapons
  :parameters ()
  :precondition (and (< (attacks-launched) 1) (>= (engineeringbay-count) 1) (>= (minerals) 100) (>= (vespene) 100)
                      (< (weapon-upgrades) 1))
  :effect (and (decrease (minerals) 100) (decrease (vespene) 100)
               (increase (weapon-upgrades) 1)))

;; Stimpack is researched at a Barracks Tech Lab, so it shares the add-on the
;; Marauders already need. Modelled as a one-shot 0/1 fluent rather than a
;; level counter because the ability does not stack.
(:action research_stimpack
  :parameters ()
  :precondition (and (< (attacks-launched) 1) (>= (techlab-barracks-count) 1) (< (stimpack) 1)
                      (>= (minerals) 100) (>= (vespene) 100))
  :effect (and (decrease (minerals) 100) (decrease (vespene) 100)
               (increase (stimpack) 1)))

  (:action train_marine
    :parameters ()
    :precondition (and (< (attacks-launched) 1)
        (>= (barracks-count) 1)
        (>= (minerals) 50)
        (>= (rax-time) 18)
        (<= (+ (supply-used) 1) (supply-cap))
    )
    :effect (and
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
  :effect (and (assign (marine-count) 0) (assign (marauder-count) 0) (assign (tank-count) 0)
               (increase (attacks-launched) 1)))
)
