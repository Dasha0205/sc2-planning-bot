;; Classical baseline for the numeric vs classical ablation (T4.1).
;;
;; The same 14 macro actions as domain_numeric_v8, in the propositional style of
;; Orava's domain_baseline.pddl: every building and unit is an object, supply is
;; a pool of slots that depots unlock (one slot per unit, whatever its size),
;; and there are no resources and no clock -- so no wait actions. Affordability
;; is left to execution: the executor refuses an order until the bank covers it.
;; The production limits of v2 are expressed by how many building objects the
;; problem declares; the attack threshold by which units the problem puts in the
;; wave (in-wave), all of which must exist before `attack`.

(define (domain sc2-terran-classical)
  (:requirements :strips :typing :negative-preconditions :universal-preconditions
                 :conditional-effects)

  (:types
    building unit slot - object
    depot barracks refinery factory ebay cc - building
    marine marauder tank - unit
  )

  (:predicates
    (built ?b - building)
    (has-techlab ?b - building)
    (unlocks ?d - building ?s - slot)
    (free ?s - slot)
    (trained ?u - unit)
    (in-wave ?u - unit)
    (weapons-researched)
    (stim-researched)
    (attacked)
  )

  (:action build_supply_depot
    :parameters (?d - depot)
    :precondition (and (not (attacked)) (not (built ?d)))
    :effect (and (built ?d) (forall (?s - slot) (when (unlocks ?d ?s) (free ?s))))
  )

  (:action build_barracks
    :parameters (?b - barracks)
    :precondition (and (not (attacked)) (not (built ?b)) (exists (?d - depot) (built ?d)))
    :effect (built ?b)
  )

  (:action build_refinery
    :parameters (?r - refinery)
    :precondition (and (not (attacked)) (not (built ?r)))
    :effect (built ?r)
  )

  (:action expand
    :parameters (?c - cc)
    :precondition (and (not (attacked)) (not (built ?c)))
    :effect (built ?c)
  )

  (:action build_factory
    :parameters (?f - factory)
    :precondition (and (not (attacked)) (not (built ?f))
                       (exists (?b - barracks) (built ?b))
                       (exists (?r - refinery) (built ?r)))
    :effect (built ?f)
  )

  (:action build_engineeringbay
    :parameters (?e - ebay)
    :precondition (and (not (attacked)) (not (built ?e)) (exists (?d - depot) (built ?d)))
    :effect (built ?e)
  )

  (:action build_techlab_barracks
    :parameters (?b - barracks)
    :precondition (and (not (attacked)) (built ?b) (not (has-techlab ?b))
                       (exists (?r - refinery) (built ?r)))
    :effect (has-techlab ?b)
  )

  (:action build_techlab_factory
    :parameters (?f - factory)
    :precondition (and (not (attacked)) (built ?f) (not (has-techlab ?f)))
    :effect (has-techlab ?f)
  )

  (:action train_marine
    :parameters (?u - marine ?s - slot)
    :precondition (and (not (attacked)) (not (trained ?u)) (free ?s)
                       (exists (?b - barracks) (built ?b)))
    :effect (and (trained ?u) (not (free ?s)))
  )

  (:action train_marauder
    :parameters (?u - marauder ?s - slot)
    :precondition (and (not (attacked)) (not (trained ?u)) (free ?s)
                       (exists (?b - barracks) (has-techlab ?b))
                       (exists (?r - refinery) (built ?r)))
    :effect (and (trained ?u) (not (free ?s)))
  )

  (:action train_siegetank
    :parameters (?u - tank ?s - slot)
    :precondition (and (not (attacked)) (not (trained ?u)) (free ?s)
                       (exists (?f - factory) (has-techlab ?f)))
    :effect (and (trained ?u) (not (free ?s)))
  )

  (:action research_weapons
    :parameters ()
    :precondition (and (not (attacked)) (not (weapons-researched))
                       (exists (?e - ebay) (built ?e))
                       (exists (?r - refinery) (built ?r)))
    :effect (weapons-researched)
  )

  (:action research_stimpack
    :parameters ()
    :precondition (and (not (attacked)) (not (stim-researched))
                       (exists (?b - barracks) (has-techlab ?b)))
    :effect (stim-researched)
  )

  (:action attack
    :parameters ()
    :precondition (and (not (attacked))
                       (forall (?u - unit) (or (not (in-wave ?u)) (trained ?u))))
    :effect (attacked)
  )
)
