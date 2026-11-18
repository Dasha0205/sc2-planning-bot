(define (problem sc2-classical)
    (:domain sc2-terran-classical)

    (:objects
        depot1 depot2 depot3 depot4 depot5 depot6 depot7 - depot
        barracks1 barracks2 barracks3 barracks4 - barracks
        refinery1 refinery2 - refinery
        factory1 - factory
        ebay1 - ebay
        cc1 cc2 cc3 - cc
        s1 s2 s3 s4 s5 s6 s7 s8 s9 s10 s11 s12 s13 s14 s15 s16 s17 s18 s19 s20 s21 s22 s23 s24 s25 - slot
        marine1 marine2 marine3 marine4 marine5 marine6 marine7 marine8 - marine
        marauder1 marauder2 marauder3 marauder4 - marauder
    )

    (:init
        (built depot1)
        (built barracks1)
        (built cc1)
        (free s1)
        (unlocks depot2 s2)
        (unlocks depot2 s3)
        (unlocks depot2 s4)
        (unlocks depot2 s5)
        (unlocks depot3 s6)
        (unlocks depot3 s7)
        (unlocks depot3 s8)
        (unlocks depot3 s9)
        (unlocks depot4 s10)
        (unlocks depot4 s11)
        (unlocks depot4 s12)
        (unlocks depot4 s13)
        (unlocks depot5 s14)
        (unlocks depot5 s15)
        (unlocks depot5 s16)
        (unlocks depot5 s17)
        (unlocks depot6 s18)
        (unlocks depot6 s19)
        (unlocks depot6 s20)
        (unlocks depot6 s21)
        (unlocks depot7 s22)
        (unlocks depot7 s23)
        (unlocks depot7 s24)
        (unlocks depot7 s25)
        (trained marine1)
        (trained marine2)
        (trained marine3)
        (trained marine4)
        (trained marine5)
        (trained marine6)
    )

    (:goal (and
        (built refinery1)
        (has-techlab barracks1)
        (trained marine1)
        (trained marine2)
        (trained marine3)
        (trained marine4)
        (trained marine5)
        (trained marine6)
        (trained marine7)
        (trained marine8)
        (trained marauder1)
        (trained marauder2)
        (trained marauder3)
        (trained marauder4)
    ))
)
