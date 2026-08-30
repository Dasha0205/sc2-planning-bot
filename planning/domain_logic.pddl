(define (domain sc2)
  (:requirements :strips)

  (:predicates
    (supply_depot_built)
    (barracks_built)
    (second_barracks_built)
    (has_army)
    (ready_for_attack)
  )

  (:action build_supply_depot
    :parameters ()
    :precondition (and)
    :effect (supply_depot_built)
  )

  (:action build_barracks
    :parameters ()
    :precondition (supply_depot_built)
    :effect (barracks_built)
  )

  (:action build_second_barracks
    :parameters ()
    :precondition (barracks_built)
    :effect (second_barracks_built)
  )

  (:action train_army
    :parameters ()
    :precondition (barracks_built)
    :effect (has_army)
  )

  (:action attack
    :parameters ()
    :precondition (has_army)
    :effect (ready_for_attack)
  )
)