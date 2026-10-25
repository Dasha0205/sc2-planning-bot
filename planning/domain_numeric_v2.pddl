;; domain_numeric_v2 (T1.7): v1 plus production limits, so that the final
;; stage goal "spend the bank" (bot/planning_bot.py STAGE_GOALS[3]) leads to
;; sensible spending instead of endless buildings. Changes against v1:
;;   build_supply_depot    only while supply-cap <= 192 (the game caps at 200)
;;   build_barracks        at most 3 per Command Center
;;   build_factory         at most 1 per Command Center
;;   build_engineeringbay  at most 1
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
)

  (:action wait_for_minerals
  :parameters () :precondition ()
  :effect (increase (minerals) (mining-rate)))

  (:action build_supply_depot
    :parameters ()
    :precondition (and
        (>= (minerals) 100)
        (<= (supply-cap) 192)
    )
    :effect (and
        (decrease (minerals) 100)
        (increase (supply-cap) 8)
        (increase (depot-count) 1) ;
    )
  )

  (:action build_barracks
    :parameters ()
    :precondition (and
        (>= (minerals) 150)
        (>= (depot-count) 1) ;
        (< (barracks-count) (* 3 (cc-count)))
    )
    :effect (and
        (decrease (minerals) 150)
        (increase (barracks-count) 1)
    )
  )

  (:action build_refinery
  :parameters ()
  :precondition (and (>= (minerals) 75) (>= (cc-count) 1)
                      (< (refinery-count) (* 2 (cc-count))))
  :effect (and (decrease (minerals) 75)
               (increase (refinery-count) 1)
               (increase (gas-rate) 25)))

(:action wait_for_vespene
  :parameters () :precondition (>= (refinery-count) 1)
  :effect (increase (vespene) (gas-rate)))

  (:action expand
  :parameters ()
  :precondition (and (>= (minerals) 400) (< (cc-count) 2))
  :effect (and (decrease (minerals) 400)
               (increase (cc-count) 1)
               (increase (mining-rate) 40)))


(:action build_factory
  :parameters ()
  :precondition (and (>= (minerals) 150) (>= (barracks-count) 1) (< (factory-count) (cc-count)))
  :effect (and (decrease (minerals) 150) (increase (factory-count) 1)))

;; Tech Lab add-ons. A Barracks or Factory can carry at most one add-on, so
;; the precondition demands a production building that does not yet have one.
;; Without these the game silently rejects every Marauder and Siege Tank
;; order: the domain would claim a unit was trained that never existed.
(:action build_techlab_barracks
  :parameters ()
  :precondition (and (>= (minerals) 50) (>= (vespene) 25)
                      (> (barracks-count) (techlab-barracks-count)))
  :effect (and (decrease (minerals) 50) (decrease (vespene) 25)
               (increase (techlab-barracks-count) 1)))

(:action build_techlab_factory
  :parameters ()
  :precondition (and (>= (minerals) 50) (>= (vespene) 25)
                      (> (factory-count) (techlab-factory-count)))
  :effect (and (decrease (minerals) 50) (decrease (vespene) 25)
               (increase (techlab-factory-count) 1)))

(:action train_marauder
  :parameters ()
  :precondition (and (>= (barracks-count) 1) (>= (techlab-barracks-count) 1)
                      (>= (minerals) 100) (>= (vespene) 25)
                      (<= (+ (supply-used) 2) (supply-cap)))
  :effect (and (decrease (minerals) 100) (decrease (vespene) 25)
               (increase (supply-used) 2) (increase (marauder-count) 1)))

(:action train_siegetank
  :parameters ()
  :precondition (and (>= (factory-count) 1) (>= (techlab-factory-count) 1)
                      (>= (minerals) 150) (>= (vespene) 125)
                      (<= (+ (supply-used) 3) (supply-cap)))
  :effect (and (decrease (minerals) 150) (decrease (vespene) 125)
               (increase (supply-used) 3) (increase (tank-count) 1)))



(:action build_engineeringbay
  :parameters ()
  :precondition (and (>= (minerals) 125) (>= (depot-count) 1) (< (engineeringbay-count) 1))
  :effect (and (decrease (minerals) 125) (increase (engineeringbay-count) 1)))

(:action research_weapons
  :parameters ()
  :precondition (and (>= (engineeringbay-count) 1) (>= (minerals) 100) (>= (vespene) 100)
                      (< (weapon-upgrades) 3))
  :effect (and (decrease (minerals) 100) (decrease (vespene) 100)
               (increase (weapon-upgrades) 1)))

;; Stimpack is researched at a Barracks Tech Lab, so it shares the add-on the
;; Marauders already need. Modelled as a one-shot 0/1 fluent rather than a
;; level counter because the ability does not stack.
(:action research_stimpack
  :parameters ()
  :precondition (and (>= (techlab-barracks-count) 1) (< (stimpack) 1)
                      (>= (minerals) 100) (>= (vespene) 100))
  :effect (and (decrease (minerals) 100) (decrease (vespene) 100)
               (increase (stimpack) 1)))

  (:action train_marine
    :parameters ()
    :precondition (and
        (>= (barracks-count) 1)
        (>= (minerals) 50)
        (<= (+ (supply-used) 1) (supply-cap))
    )
    :effect (and
        (decrease (minerals) 50)
        (increase (supply-used) 1)
        (increase (marine-count) 1)
    )
  )

  ;; Army value is weighted by unit strength: a Marauder counts as two
  ;; Marines and a Siege Tank as three. Committing the army resets all
  ;; three counters, so the planner must rebuild before attacking again.
  ;;
  ;; The threshold of 20 is the single knob controlling how big a force the
  ;; planner masses before committing it. attacks-launched exists so that
  ;; "commit an attack" is expressible as a goal: the problem generator always
  ;; initialises it to 0, so a goal of (>= (attacks-launched) 1) means "launch
  ;; one more wave", and satisfying it forces the planner to build the army
  ;; first. That is what keeps the attack decision inside the planner.
  (:action attack
  :parameters ()
  :precondition (>= (+ (marine-count) (+ (* 2 (marauder-count)) (* 3 (tank-count)))) 20)
  :effect (and (assign (marine-count) 0) (assign (marauder-count) 0) (assign (tank-count) 0)
               (increase (attacks-launched) 1)))
)