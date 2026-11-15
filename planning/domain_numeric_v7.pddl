;; domain_numeric_v7: v6 with one clock (review of T8.2). A wait is 5 s of game
;; time whichever resource it waits for, so every wait now banks minerals AND gas
;; AND production seconds. In v6 a gas wait added production time without the
;; minerals mined meanwhile, so the planner used gas waits as free clock ticks and
;; under-counted income by 600-1 300 minerals per plan. Production capacity as in
;; v6: (rax-time) / (factory-time) production seconds, +5 per Barracks / Factory on
;; every wait, Marine 18 / Marauder 21 / Siege Tank 32 s per unit. Simplifications:
;; one pool for all Barracks (a Marauder may draw on one without a Tech Lab), idle
;; time accumulates without the real queue limit, buildings produce from the
;; moment they are ordered.
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
    (rax-time) (factory-time)
)

  (:action wait_for_minerals
  :parameters () :precondition ()
  :effect (and (increase (minerals) (mining-rate))
               (increase (vespene) (gas-rate))
               (increase (rax-time) (* 5 (barracks-count)))
               (increase (factory-time) (* 5 (factory-count)))))

  (:action build_supply_depot
    :parameters ()
    :precondition (and
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
  :effect (and (increase (vespene) (gas-rate))
               (increase (minerals) (mining-rate))
               (increase (rax-time) (* 5 (barracks-count)))
               (increase (factory-time) (* 5 (factory-count)))))

  (:action expand
  :parameters ()
  :precondition (and (>= (minerals) 400) (< (cc-count) 2))
  :effect (and (decrease (minerals) 400)
               (increase (cc-count) 1)
               (increase (mining-rate) 40)))


(:action build_factory
  :parameters ()
  :precondition (and (>= (minerals) 150) (>= (vespene) 100) (>= (barracks-count) 1)
                      (< (factory-count) (cc-count)))
  :effect (and (decrease (minerals) 150) (decrease (vespene) 100) (increase (factory-count) 1)))

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
                      (>= (minerals) 100) (>= (vespene) 25) (>= (rax-time) 21)
                      (<= (+ (supply-used) 2) (supply-cap)))
  :effect (and (decrease (minerals) 100) (decrease (vespene) 25) (decrease (rax-time) 21)
               (increase (supply-used) 2) (increase (marauder-count) 1)))

(:action train_siegetank
  :parameters ()
  :precondition (and (>= (factory-count) 1) (>= (techlab-factory-count) 1)
                      (>= (minerals) 150) (>= (vespene) 125) (>= (factory-time) 32)
                      (<= (+ (supply-used) 3) (supply-cap)))
  :effect (and (decrease (minerals) 150) (decrease (vespene) 125) (decrease (factory-time) 32)
               (increase (supply-used) 3) (increase (tank-count) 1)))



(:action build_engineeringbay
  :parameters ()
  :precondition (and (>= (minerals) 125) (>= (depot-count) 1) (< (engineeringbay-count) 1))
  :effect (and (decrease (minerals) 125) (increase (engineeringbay-count) 1)))

(:action research_weapons
  :parameters ()
  :precondition (and (>= (engineeringbay-count) 1) (>= (minerals) 100) (>= (vespene) 100)
                      (< (weapon-upgrades) 1))
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
