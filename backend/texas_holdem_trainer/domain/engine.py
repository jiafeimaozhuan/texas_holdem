from __future__ import annotations

from texas_holdem_trainer.domain.actions import ActionType, LegalAction
from texas_holdem_trainer.domain.cards import Deck
from texas_holdem_trainer.domain.evaluator import HandRank, evaluate_best
from texas_holdem_trainer.domain.state import GameState, PlayerState, Street


ACTIVE_STREETS = {Street.PREFLOP, Street.FLOP, Street.TURN, Street.RIVER}


class PokerEngine:
    def create_table(
        self,
        table_id: str,
        player_names: list[str],
        human_seat: int,
        starting_stack: int,
        small_blind: int,
        big_blind: int,
        seed: int | None = None,
    ) -> GameState:
        if len(player_names) < 2:
            raise ValueError("at least two players are required")
        if not 0 <= human_seat < len(player_names):
            raise ValueError("human_seat must identify a player")
        if starting_stack <= 0:
            raise ValueError("starting_stack must be positive")
        if small_blind <= 0 or big_blind <= 0:
            raise ValueError("blinds must be positive")
        if small_blind > big_blind:
            raise ValueError("small_blind must be less than or equal to big_blind")

        players = [
            PlayerState(
                seat=seat,
                name=name,
                stack=starting_stack,
                is_human=seat == human_seat,
            )
            for seat, name in enumerate(player_names)
        ]
        return GameState(
            table_id=table_id,
            players=players,
            dealer_seat=0,
            small_blind=small_blind,
            big_blind=big_blind,
            min_raise=big_blind,
            seed=seed,
        )

    def start_hand(self, state: GameState) -> GameState:
        if state.street not in {Street.WAITING, Street.COMPLETE}:
            raise ValueError("cannot start a hand while another hand is active")
        if len([player for player in state.players if player.stack > 0]) < 2:
            raise ValueError("at least two players with chips are required")

        if state.hand_number > 0:
            state.dealer_seat = self._next_seat_with_stack(state, state.dealer_seat)
        state.hand_number += 1

        state.deck = Deck.new_shuffled(seed=self._hand_seed(state))
        state.street = Street.PREFLOP
        state.board.clear()
        state.pot = 0
        state.current_bet = 0
        state.min_raise = state.big_blind
        state.current_actor_seat = None
        state.hand_history = [
            {
                "type": "hand_started",
                "hand_number": state.hand_number,
                "dealer_seat": state.dealer_seat,
            }
        ]

        for player in state.players:
            player.hole_cards.clear()
            player.folded = player.stack <= 0
            player.all_in = player.stack == 0
            player.street_bet = 0
            player.total_committed = 0
            player.acted_this_street = False

        small_blind_seat, big_blind_seat = self._blind_seats(state)
        self._post_blind(state, small_blind_seat, state.small_blind, "small_blind")
        self._post_blind(state, big_blind_seat, state.big_blind, "big_blind")
        self._deal_hole_cards(state)

        state.current_actor_seat = self._first_preflop_actor(state, big_blind_seat)
        if not self._can_continue_betting(state):
            state.current_actor_seat = None
            self._resolve_after_action(state)
        return state

    def legal_actions(self, state: GameState, seat: int) -> list[LegalAction]:
        if (
            state.street not in ACTIVE_STREETS
            or state.current_actor_seat is None
            or seat != state.current_actor_seat
            or not 0 <= seat < len(state.players)
        ):
            return []

        player = state.players[seat]
        if player.folded or player.all_in or player.stack <= 0:
            return []

        call_amount = max(0, state.current_bet - player.street_bet)
        can_be_called = self._has_other_player_who_can_respond(state, seat)
        actions: list[LegalAction] = []

        if call_amount > 0:
            actions.append(LegalAction(ActionType.FOLD))
            actions.append(
                LegalAction(
                    ActionType.CALL,
                    min_amount=min(call_amount, player.stack),
                    max_amount=min(call_amount, player.stack),
                )
            )
            min_raise_amount = state.current_bet + state.min_raise - player.street_bet
            if can_be_called and player.stack >= min_raise_amount:
                actions.append(
                    LegalAction(
                        ActionType.RAISE,
                        min_amount=min_raise_amount,
                        max_amount=player.stack,
                    )
                )
        else:
            actions.append(LegalAction(ActionType.CHECK))
            if player.stack >= state.min_raise:
                actions.append(
                    LegalAction(
                        ActionType.BET,
                        min_amount=state.min_raise,
                        max_amount=player.stack,
                    )
                )

        if player.stack > 0 and (can_be_called or player.stack <= call_amount):
            actions.append(
                LegalAction(
                    ActionType.ALL_IN,
                    min_amount=player.stack,
                    max_amount=player.stack,
                )
            )
        return actions

    def apply_action(
        self,
        state: GameState,
        seat: int,
        action: ActionType,
        amount: int = 0,
    ) -> GameState:
        if state.street not in ACTIVE_STREETS:
            raise ValueError("hand is not accepting actions")
        if seat != state.current_actor_seat:
            raise ValueError("seat is not the current actor")
        if not 0 <= seat < len(state.players):
            raise ValueError("seat is out of range")
        if not isinstance(amount, int) or isinstance(amount, bool):
            raise TypeError("amount must be an integer")
        if amount < 0:
            raise ValueError("amount must be non-negative")

        player = state.players[seat]
        if player.folded or player.all_in or player.stack <= 0:
            raise ValueError("player cannot act")

        call_amount = max(0, state.current_bet - player.street_bet)
        committed = 0

        if action is ActionType.FOLD:
            player.folded = True
        elif action is ActionType.CHECK:
            if call_amount != 0:
                raise ValueError("cannot check while facing a bet")
        elif action is ActionType.CALL:
            if call_amount == 0:
                raise ValueError("cannot call without facing a bet")
            committed = self._commit(state, player, min(call_amount, player.stack))
        elif action is ActionType.BET:
            if call_amount != 0:
                raise ValueError("cannot bet while facing a bet")
            if not self._has_other_player_who_can_respond(state, seat):
                raise ValueError("cannot commit uncallable chips")
            if amount < state.min_raise:
                raise ValueError("bet amount is below the minimum bet")
            committed = self._commit_aggressive(state, player, amount)
        elif action is ActionType.RAISE:
            if call_amount == 0:
                raise ValueError("cannot raise without facing a bet")
            if not self._has_other_player_who_can_respond(state, seat):
                raise ValueError("cannot commit uncallable chips")
            min_raise_amount = state.current_bet + state.min_raise - player.street_bet
            if amount < min_raise_amount:
                raise ValueError("raise amount is below the minimum raise")
            committed = self._commit_aggressive(state, player, amount)
        elif action is ActionType.ALL_IN:
            all_in_amount = player.stack if amount == 0 else amount
            if all_in_amount != player.stack:
                raise ValueError("all-in amount must equal the player's stack")
            if (
                all_in_amount > call_amount
                and not self._has_other_player_who_can_respond(state, seat)
            ):
                raise ValueError("cannot commit uncallable chips")
            committed = self._commit_aggressive(state, player, all_in_amount)
        else:
            raise ValueError(f"unsupported action: {action}")

        player.acted_this_street = True
        state.hand_history.append(
            {
                "type": "action",
                "street": state.street.value,
                "seat": seat,
                "action": action.value,
                "amount": committed,
            }
        )
        self._resolve_after_action(state)
        return state

    def _hand_seed(self, state: GameState) -> int | None:
        if state.seed is None:
            return None
        return state.seed + state.hand_number - 1

    def _blind_seats(self, state: GameState) -> tuple[int, int]:
        if len(self._players_dealt_in(state)) == 2:
            button = state.dealer_seat
            if state.players[button].stack <= 0:
                button = self._next_seat_with_stack(state, button)
                state.dealer_seat = button
            return button, self._next_seat_with_stack(state, button)
        small_blind = self._next_seat_with_stack(state, state.dealer_seat)
        big_blind = self._next_seat_with_stack(state, small_blind)
        return small_blind, big_blind

    def _post_blind(
        self,
        state: GameState,
        seat: int,
        amount: int,
        blind_name: str,
    ) -> None:
        player = state.players[seat]
        committed = self._commit(state, player, amount)
        state.current_bet = max(state.current_bet, player.street_bet)
        state.hand_history.append(
            {
                "type": "blind",
                "seat": seat,
                "blind": blind_name,
                "amount": committed,
            }
        )

    def _deal_hole_cards(self, state: GameState) -> None:
        if state.deck is None:
            raise ValueError("cannot deal without a deck")
        for player in state.players:
            if not player.folded:
                player.hole_cards.extend(state.deck.deal(2))
        state.hand_history.append({"type": "deal", "cards": "hole"})

    def _deal_board(self, state: GameState, street: Street) -> None:
        if state.deck is None:
            raise ValueError("cannot deal without a deck")
        card_count = 3 if street is Street.FLOP else 1
        state.board.extend(state.deck.deal(card_count))
        state.hand_history.append(
            {
                "type": "street",
                "street": street.value,
                "board_count": len(state.board),
            }
        )

    def _commit(self, state: GameState, player: PlayerState, amount: int) -> int:
        committed = player.commit_chips(amount)
        state.pot += committed
        return committed

    def _commit_aggressive(
        self,
        state: GameState,
        player: PlayerState,
        amount: int,
    ) -> int:
        if amount <= 0:
            raise ValueError("amount must be positive")
        if amount > player.stack:
            raise ValueError("amount cannot exceed player's stack")

        old_current_bet = state.current_bet
        old_min_raise = state.min_raise
        committed = self._commit(state, player, amount)
        if player.street_bet > old_current_bet:
            increase = player.street_bet - old_current_bet
            state.current_bet = player.street_bet
            if increase >= old_min_raise:
                state.min_raise = increase
            for other in state.players:
                if other.seat != player.seat and not other.folded and not other.all_in:
                    other.acted_this_street = False
        return committed

    def _resolve_after_action(self, state: GameState) -> None:
        while True:
            remaining = [player for player in state.players if not player.folded]
            if len(remaining) == 1:
                self._settle_fold_winner(state, remaining[0])
                return

            if state.street not in ACTIVE_STREETS:
                state.current_actor_seat = None
                return

            if (
                not self._can_continue_betting(state)
                and not self._has_pending_call_decision(state)
            ):
                if state.street is Street.RIVER:
                    self._settle_showdown(state)
                    return
                self._advance_street(state)
                continue

            if self._betting_round_complete(state):
                if state.street is Street.RIVER:
                    self._settle_showdown(state)
                    return
                self._advance_street(state)
                if self._can_continue_betting(state):
                    return
                continue

            state.current_actor_seat = self._next_actionable_seat(
                state,
                state.current_actor_seat,
            )
            return

    def _advance_street(self, state: GameState) -> None:
        next_street = {
            Street.PREFLOP: Street.FLOP,
            Street.FLOP: Street.TURN,
            Street.TURN: Street.RIVER,
        }[state.street]

        state.street = next_street
        state.current_bet = 0
        state.min_raise = state.big_blind
        for player in state.players:
            player.street_bet = 0
            player.acted_this_street = False

        self._deal_board(state, next_street)
        state.current_actor_seat = self._first_postflop_actor(state)

    def _betting_round_complete(self, state: GameState) -> bool:
        actionable_players = [
            player
            for player in state.players
            if not player.folded and not player.all_in and player.stack > 0
        ]
        if not actionable_players:
            return True
        return all(
            player.acted_this_street and player.street_bet == state.current_bet
            for player in actionable_players
        )

    def _can_continue_betting(self, state: GameState) -> bool:
        return (
            sum(
                1
                for player in state.players
                if not player.folded and not player.all_in and player.stack > 0
            )
            >= 2
        )

    def _has_pending_call_decision(self, state: GameState) -> bool:
        return any(
            not player.folded
            and not player.all_in
            and player.stack > 0
            and player.street_bet < state.current_bet
            for player in state.players
        )

    def _has_other_player_who_can_respond(self, state: GameState, seat: int) -> bool:
        return any(
            player.seat != seat
            and not player.folded
            and not player.all_in
            and player.stack > 0
            for player in state.players
        )

    def _first_preflop_actor(
        self,
        state: GameState,
        big_blind_seat: int,
    ) -> int | None:
        if len(self._players_dealt_in(state)) == 2:
            candidate = state.players[state.dealer_seat]
            if not candidate.folded and not candidate.all_in and candidate.stack > 0:
                return state.dealer_seat
            return self._next_actionable_seat(state, state.dealer_seat)
        return self._next_actionable_seat(state, big_blind_seat)

    def _players_dealt_in(self, state: GameState) -> list[PlayerState]:
        return [player for player in state.players if not player.folded]

    def _first_postflop_actor(self, state: GameState) -> int | None:
        return self._next_actionable_seat(state, state.dealer_seat)

    def _next_actionable_seat(
        self,
        state: GameState,
        after_seat: int | None,
    ) -> int | None:
        if after_seat is None:
            after_seat = state.dealer_seat
        for offset in range(1, len(state.players) + 1):
            seat = (after_seat + offset) % len(state.players)
            player = state.players[seat]
            if not player.folded and not player.all_in and player.stack > 0:
                return seat
        return None

    def _next_seat_with_stack(self, state: GameState, after_seat: int) -> int:
        for offset in range(1, len(state.players) + 1):
            seat = (after_seat + offset) % len(state.players)
            if state.players[seat].stack > 0:
                return seat
        raise ValueError("no player with chips found")

    def _settle_fold_winner(self, state: GameState, winner: PlayerState) -> None:
        pot = state.pot
        winner.stack += pot
        state.pot = 0
        state.street = Street.COMPLETE
        state.current_actor_seat = None
        state.hand_history.append(
            {
                "type": "settlement",
                "winners": [winner.seat],
                "pot": pot,
                "reason": "fold",
            }
        )

    def _settle_showdown(self, state: GameState) -> None:
        state.street = Street.SHOWDOWN
        contenders = [player for player in state.players if not player.folded]
        ranks: dict[int, HandRank] = {
            player.seat: evaluate_best([*player.hole_cards, *state.board])
            for player in contenders
        }
        best_rank = max(ranks.values())
        winners = sorted(seat for seat, rank in ranks.items() if rank == best_rank)
        state.hand_history.append(
            {
                "type": "showdown",
                "ranks": {
                    seat: {
                        "category": rank.category.name,
                        "tiebreakers": rank.tiebreakers,
                    }
                    for seat, rank in ranks.items()
                },
                "winners": winners,
            }
        )

        pot = state.pot
        share, remainder = divmod(pot, len(winners))
        for index, seat in enumerate(winners):
            state.players[seat].stack += share + (1 if index < remainder else 0)
        state.pot = 0
        state.street = Street.COMPLETE
        state.current_actor_seat = None
        state.hand_history.append(
            {
                "type": "settlement",
                "winners": winners,
                "pot": pot,
                "share": share,
                "remainder": remainder,
            }
        )
