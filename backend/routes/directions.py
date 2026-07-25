"""
/api/routes — Smart route suggestion with traffic distribution
"""

from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timezone
from models.schemas import RouteRequest, RoutesResponse
from services import tomtom, analyzer, geocoder, cache
from services.distributor import distributor
from services.live_feed import live_feed
from services import nlu
import uuid

router = APIRouter()


async def _fetch_and_assign_routes(
    origin: str,
    destination: str,
    mode: str = "car",
    alternatives: int = 3,
    user_id: str = None,
) -> dict:
    """
    Core routing logic, deliberately a plain function (no FastAPI Query()
    defaults) so it can be called directly from other endpoints — like
    /smart below — without Query objects leaking through as unresolved
    defaults, which is a real bug that happens if you call an
    @router.get-decorated function directly instead of through a request.
    """
    if not user_id:
        user_id = str(uuid.uuid4())[:8]

    cache_key = cache.route_key(origin, destination, mode)
    cached_routes = cache.get(cache_key + ":routes")

    if not cached_routes:
        origin_coords = await geocoder.geocode(origin)
        dest_coords   = await geocoder.geocode(destination)

        if not origin_coords:
            raise HTTPException(status_code=400, detail=f"Could not find: '{origin}'")
        if not dest_coords:
            raise HTTPException(status_code=400, detail=f"Could not find: '{destination}'")

        origin_str = geocoder.coords_to_string(*origin_coords)
        dest_str   = geocoder.coords_to_string(*dest_coords)

        raw = await tomtom.fetch_routes(origin_str, dest_str, mode, alternatives)
        if raw and "routes" in raw:
            routes = [analyzer.parse_tomtom_route(r, i+1) for i, r in enumerate(raw["routes"])]
        else:
            routes = analyzer.generate_mock_routes(origin, destination)

        routes = analyzer.sort_routes_by_traffic(routes)
        for i, r in enumerate(routes):
            r.route_id = i + 1

        routes_dicts = [r.model_dump() for r in routes]
        cache.set(cache_key + ":routes", routes_dicts, ttl=60)
        cached_routes = routes_dicts

    # Blend in any live YOLO26 camera reports (always re-applied, even on a
    # cache hit, so fresh camera data shows up without waiting for the
    # 60s route cache to expire).
    live_reports = live_feed.all_reports()
    if live_reports:
        rebuilt = [
            analyzer.RouteOption(**r) if not isinstance(r, analyzer.RouteOption) else r
            for r in cached_routes
        ]
        rebuilt = analyzer.apply_live_camera_data(rebuilt, live_reports)
        rebuilt = analyzer.sort_routes_by_traffic(rebuilt)
        for i, r in enumerate(rebuilt):
            r.route_id = i + 1
        cached_routes = [r.model_dump() for r in rebuilt]

    assignment   = distributor.assign_route(user_id, origin, destination, cached_routes)
    load_summary = distributor.get_load_summary(origin, destination)

    return {
        "user_id": user_id,
        "origin": origin,
        "destination": destination,
        "assigned_route": assignment["route"],
        "reason": assignment["reason"],
        "active_users_on_route": assignment["active_users_on_route"],
        "all_routes": cached_routes,
        "route_loads": load_summary,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("", response_model=None)
async def get_routes(
    origin: str = Query(...),
    destination: str = Query(...),
    mode: str = Query("car"),
    alternatives: int = Query(3, ge=1, le=3),
    user_id: str = Query(None),
):
    return await _fetch_and_assign_routes(origin, destination, mode, alternatives, user_id)


@router.post("", response_model=None)
async def post_routes(body: RouteRequest):
    return await _fetch_and_assign_routes(
        origin=body.origin,
        destination=body.destination,
        mode=body.travel_mode,
        alternatives=body.max_alternatives,
    )


@router.delete("/release")
async def release_route(user_id: str = Query(...), actual_minutes: float = Query(None)):
    distributor.release_route(user_id, actual_minutes)
    return {"message": "Route released", "user_id": user_id}


@router.get("/bandit-stats")
async def get_bandit_stats():
    """
    Exposes what the learned weighting bandit currently believes is the best
    congestion/load balance, and how many real trips have informed that —
    mainly useful for demoing that the weighting adapts instead of being a
    fixed constant.
    """
    from services.bandit import weight_bandit
    return {"arms": weight_bandit.stats()}


@router.get("/smart", response_model=None)
async def get_smart_route(
    query: str = Query(..., description="Free-text request, e.g. 'fastest way to Whitefield from Koramangala avoiding tolls'"),
    origin_fallback: str = Query(None, description="Used as origin if the text doesn't mention one (e.g. current GPS location)"),
    user_id: str = Query(None),
):
    """
    Natural-language front door to routing. Parses free text into
    origin/destination/avoid-preferences (via Claude if ANTHROPIC_API_KEY is
    set, otherwise a regex-based fallback — see services/nlu.py), then runs
    the exact same routing + distribution pipeline as the structured
    /api/routes endpoint, plus demotes any route matching an avoid term.
    """
    parsed = nlu.parse_request(query)

    destination = parsed.get("destination")
    origin = parsed.get("origin") or origin_fallback

    if not destination:
        raise HTTPException(status_code=400, detail="Couldn't find a destination in that request — try including 'to <place>'.")
    if not origin:
        raise HTTPException(status_code=400, detail="Couldn't find an origin, and no current location was provided — try including 'from <place>'.")

    result = await _fetch_and_assign_routes(origin=origin, destination=destination, user_id=user_id)

    avoid_terms = parsed.get("avoid", [])
    if avoid_terms:
        routes = [analyzer.RouteOption(**r) for r in result["all_routes"]]
        routes = analyzer.apply_avoid_preferences(routes, avoid_terms)
        routes = analyzer.sort_routes_with_avoidance(routes)
        for i, r in enumerate(routes):
            r.route_id = i + 1
        result["all_routes"] = [r.model_dump() for r in routes]
        # Re-pick the top (non-avoided-if-possible) route as the assignment,
        # since avoidance can change which route should now be recommended.
        result["assigned_route"] = result["all_routes"][0]

    result["parsed_query"] = parsed
    return result
