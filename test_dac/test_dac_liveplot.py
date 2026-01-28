import json
import numpy as np
import matplotlib.pyplot as plt
from labrad.wrappers import connectAsync
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks


# Ramp configuration --------------------------------------------------------
DAC_PORTS = [4, 5]
ADC_PORTS = [6, 7]

START_POINT = [0.0, 0.0]
FAST_AXIS_VECTOR = [3.0, 2.0]
SLOW_AXIS_VECTOR = [2.0, 5.0]

STEPS_FAST = 500
STEPS_SLOW = 50
RETRACE = False
SNAKE = False
NUM_ADC_AVERAGES = 1
DAC_PERIOD_US = 500.0
DAC_SETTLING_US = 100.0

# Indices identifying which DAC coordinates are visualized on each axis.
FAST_AXIS_INDEX = 0
SLOW_AXIS_INDEX = 1

# Derived quantities
TOTAL_LINES = STEPS_SLOW * (2 if RETRACE and not SNAKE else 1)
POINTS_PER_LINE = STEPS_FAST
NUM_ADC_CHANNELS = len(ADC_PORTS)
DISPLAY_ADC_INDEX = 1  # index into ADC channel list for plotting
current_adc_ports = list(ADC_PORTS)
current_dac_ports = list(DAC_PORTS)

NUM_DAC_CHANNELS = len(DAC_PORTS)
AXIS_TICK_COUNT = 6


def _ensure_length(values, length):
    arr = np.zeros(length, dtype=float)
    if values is None:
        return arr
    limit = min(length, len(values))
    for idx in range(limit):
        arr[idx] = float(values[idx])
    return arr


PLANE_START = _ensure_length(START_POINT, NUM_DAC_CHANNELS)
PLANE_FAST = _ensure_length(FAST_AXIS_VECTOR, NUM_DAC_CHANNELS)
PLANE_SLOW = _ensure_length(SLOW_AXIS_VECTOR, NUM_DAC_CHANNELS)
WINDOW_X_RANGE = (0.0, 1.0)
WINDOW_Y_RANGE = (0.0, 1.0)


def _plane_bounds(start, fast, slow, axis_index):
    if not (0 <= axis_index < len(start)):
        return (0.0, 1.0)
    pts = [
        start[axis_index],
        start[axis_index] + fast[axis_index],
        start[axis_index] + slow[axis_index],
        start[axis_index] + fast[axis_index] + slow[axis_index],
    ]
    return min(pts), max(pts)


def _plane_extent():
    if not (0 <= FAST_AXIS_INDEX < len(PLANE_START)) or not (
        0 <= SLOW_AXIS_INDEX < len(PLANE_START)
    ):
        return (0.0, 1.0, 0.0, 1.0)
    corners = np.array(
        [
            PLANE_START,
            PLANE_START + PLANE_FAST,
            PLANE_START + PLANE_SLOW,
            PLANE_START + PLANE_FAST + PLANE_SLOW,
        ]
    )
    xs = corners[:, FAST_AXIS_INDEX]
    ys = corners[:, SLOW_AXIS_INDEX]
    return np.nanmin(xs), np.nanmax(xs), np.nanmin(ys), np.nanmax(ys)


def _padded_ranges(x_min, x_max, y_min, y_max, pad_fraction=0.03):
    """
    Add minimal padding to the data extent. Keep the ranges tight to the actual data.
    """
    x_lower = min(x_min, x_max)
    x_upper = max(x_min, x_max)
    y_lower = min(y_min, y_max)
    y_upper = max(y_min, y_max)

    x_span = x_upper - x_lower
    y_span = y_upper - y_lower

    # Add small padding proportional to each axis's span
    x_pad = pad_fraction * max(x_span, 1e-6)
    y_pad = pad_fraction * max(y_span, 1e-6)
    
    x_lower -= x_pad
    x_upper += x_pad
    y_lower -= y_pad
    y_upper += y_pad

    return (x_lower, x_upper), (y_lower, y_upper)


def _update_axis_bounds():
    global fast_axis_min, fast_axis_max, slow_axis_min, slow_axis_max
    global WINDOW_X_RANGE, WINDOW_Y_RANGE
    fast_axis_min, fast_axis_max = _plane_bounds(
        PLANE_START, PLANE_FAST, PLANE_SLOW, FAST_AXIS_INDEX
    )
    slow_axis_min, slow_axis_max = _plane_bounds(
        PLANE_START, PLANE_FAST, PLANE_SLOW, SLOW_AXIS_INDEX
    )
    x_min, x_max, y_min, y_max = _plane_extent()
    WINDOW_X_RANGE, WINDOW_Y_RANGE = _padded_ranges(
        x_min, x_max, y_min, y_max
    )


fast_axis_min = fast_axis_max = 0.0
slow_axis_min = slow_axis_max = 0.0
_update_axis_bounds()

FAST_DAC_VIS = (
    DAC_PORTS[FAST_AXIS_INDEX] if 0 <= FAST_AXIS_INDEX < len(DAC_PORTS) else None
)
SLOW_DAC_VIS = (
    DAC_PORTS[SLOW_AXIS_INDEX] if 0 <= SLOW_AXIS_INDEX < len(DAC_PORTS) else None
)

# Buffers for incoming data
line_buffer = np.full((TOTAL_LINES, NUM_ADC_CHANNELS, POINTS_PER_LINE), np.nan)
received_lines = np.zeros(TOTAL_LINES, dtype=bool)
line_x_coords = np.full((TOTAL_LINES, POINTS_PER_LINE), np.nan)
line_y_coords = np.full((TOTAL_LINES, POINTS_PER_LINE), np.nan)

# Matplotlib setup ----------------------------------------------------------
plt.ion()
# Make figure wider to account for colorbar so the actual plot area is square
fig, ax = plt.subplots(figsize=(7.5, 6))
# Use pcolormesh for smooth interpolation instead of scatter
from matplotlib.collections import QuadMesh
import matplotlib.tri as mtri
# Initialize with empty data - we'll update with triangulation
mesh = None
cbar = None
# Keep plot area visually square - aspect will be set by data, not enforced geometrically
ax.set_aspect("auto")
ax.set_xlabel(
    f"DAC {FAST_DAC_VIS} voltage (V)" if FAST_DAC_VIS is not None else "Fast axis"
)
ax.set_ylabel(
    f"DAC {SLOW_DAC_VIS} voltage (V)" if SLOW_DAC_VIS is not None else "Slow axis"
)
fig.tight_layout()
fig.subplots_adjust(top=0.88)

ax.set_xlim(*WINDOW_X_RANGE)
ax.set_ylim(*WINDOW_Y_RANGE)


def parse_signal_payload(payload):
    """Decode JSON payload emitted by sig2DRampLine."""
    if isinstance(payload, (list, tuple)):
        payload = payload[0]
    data = json.loads(payload)

    line_index = int(data.get("line_index", 0))
    slow_param = data.get("slow_param")
    fast_direction = data.get("fast_direction", data.get("direction", "forward"))
    slow_position = data.get("slow_position")
    if slow_position is None:
        slow_position = data.get("slow_voltages", [])
    channel_data = data.get("channels", [])
    adc_ports = data.get("adc_ports", current_adc_ports)
    dac_ports = data.get("dac_ports", current_dac_ports)
    start_point = data.get("start_point")
    fast_axis_vector = data.get("fast_axis_vector")
    slow_axis_vector = data.get("slow_axis_vector")
    return (
        line_index,
        slow_param,
        fast_direction,
        slow_position,
        channel_data,
        adc_ports,
        dac_ports,
        start_point,
        fast_axis_vector,
        slow_axis_vector,
    )


def update_plot(line_idx, channel_data, x_line, y_line):
    """Update buffers and the live interpolated plot with the new line data."""
    global mesh, cbar
    
    for ch_idx, values in enumerate(channel_data):
        if ch_idx >= NUM_ADC_CHANNELS:
            continue
        if not values:
            continue
        truncated = values[:POINTS_PER_LINE]
        length = min(len(truncated), POINTS_PER_LINE)
        line_buffer[line_idx, ch_idx, :length] = truncated[:length]

    received_lines[line_idx] = True
    line_x_coords[line_idx, :] = np.nan
    line_y_coords[line_idx, :] = np.nan
    if x_line.size:
        coord_len = min(len(x_line), POINTS_PER_LINE)
        line_x_coords[line_idx, :coord_len] = x_line[:coord_len]
    if y_line.size:
        coord_len = min(len(y_line), POINTS_PER_LINE)
        line_y_coords[line_idx, :coord_len] = y_line[:coord_len]

    adc_slice = line_buffer[:, DISPLAY_ADC_INDEX, :]
    mask = (
        received_lines[:, None]
        & np.isfinite(adc_slice)
        & np.isfinite(line_x_coords)
        & np.isfinite(line_y_coords)
    )

    if np.any(mask):
        x_vals = line_x_coords[mask]
        y_vals = line_y_coords[mask]
        z_vals = adc_slice[mask]

        # Need at least 3 non-collinear points for triangulation
        if len(x_vals) < 3:
            return

        # Clear previous mesh
        if mesh is not None:
            mesh.remove()
        
        try:
            # Create triangulation for smooth interpolation
            triang = mtri.Triangulation(x_vals, y_vals)
            mesh = ax.tripcolor(triang, z_vals, cmap="viridis", shading="gouraud")
            
            # Create or update colorbar
            if cbar is None:
                cbar = fig.colorbar(mesh, ax=ax, label="Voltage (V)")
            else:
                cbar.update_normal(mesh)

            finite_vals = z_vals[np.isfinite(z_vals)]
            if finite_vals.size:
                vmin = np.min(finite_vals)
                vmax = np.max(finite_vals)
                if vmin == vmax:
                    delta = abs(vmin) * 0.05 if vmin else 1e-6
                    vmin -= delta
                    vmax += delta
                mesh.set_clim(vmin, vmax)
        except RuntimeError:
            # Triangulation failed (collinear points, etc.) - skip this update
            return

        ax.set_xlim(*WINDOW_X_RANGE)
        ax.set_ylim(*WINDOW_Y_RANGE)

        xticks = np.linspace(
            WINDOW_X_RANGE[0], WINDOW_X_RANGE[1], AXIS_TICK_COUNT
        )
        ax.set_xticks(xticks)
        ax.set_xticklabels([f"{tick:.2f}" for tick in xticks])

        yticks = np.linspace(
            WINDOW_Y_RANGE[0], WINDOW_Y_RANGE[1], AXIS_TICK_COUNT
        )
        ax.set_yticks(yticks)
        ax.set_yticklabels([f"{tick:.2f}" for tick in yticks])

    fig.canvas.draw_idle()
    
    waitTime = min(DAC_PERIOD_US * STEPS_FAST / 1e6 / 2, 0.001)
    plt.pause(waitTime)


def on_line(context, payload):
    """Signal handler for sig2DRampLine."""
    try:
        (
            line_idx,
            slow_param,
            fast_direction,
            slow_position,
            channel_data,
            adc_ports,
            dac_ports,
            start_point_payload,
            fast_axis_payload,
            slow_axis_payload,
        ) = parse_signal_payload(payload)
    except Exception as exc:
        print(f"Failed to parse payload: {payload!r} ({exc})")
        return

    global current_adc_ports, current_dac_ports
    global PLANE_START, PLANE_FAST, PLANE_SLOW
    current_adc_ports = list(adc_ports)
    current_dac_ports = list(dac_ports)

    channel_count = len(current_dac_ports)
    if start_point_payload is not None:
        PLANE_START = _ensure_length(start_point_payload, channel_count)
    if fast_axis_payload is not None:
        PLANE_FAST = _ensure_length(fast_axis_payload, channel_count)
    if slow_axis_payload is not None:
        PLANE_SLOW = _ensure_length(slow_axis_payload, channel_count)
    _update_axis_bounds()

    if line_idx >= TOTAL_LINES:
        print(f"Ignoring line {line_idx}; exceeds expected total ({TOTAL_LINES})")
        return

    if slow_position and len(slow_position) == channel_count:
        slow_position_arr = np.array(slow_position, dtype=float)
    else:
        if slow_param is not None:
            slow_position_arr = PLANE_START + float(slow_param) * PLANE_SLOW
        else:
            slow_position_arr = PLANE_START.copy()

    length_candidates = [len(values) for values in channel_data if values]
    if length_candidates:
        length = min(POINTS_PER_LINE, max(length_candidates))
    else:
        length = 0

    direction_label = (
        fast_direction if isinstance(fast_direction, str) else "forward"
    )
    direction_norm = direction_label.lower()

    if length <= 0:
        x_line = np.array([], dtype=float)
        y_line = np.array([], dtype=float)
    else:
        fast_fraction = np.linspace(0.0, 1.0, length)
        if direction_norm == "backward":
            fast_fraction = fast_fraction[::-1]

        if 0 <= FAST_AXIS_INDEX < len(slow_position_arr):
            fast_component = PLANE_FAST[FAST_AXIS_INDEX]
            x_base = slow_position_arr[FAST_AXIS_INDEX]
            x_line = x_base + fast_fraction * fast_component
        else:
            x_line = np.zeros(length, dtype=float)

        if 0 <= SLOW_AXIS_INDEX < len(slow_position_arr):
            slow_component = PLANE_FAST[SLOW_AXIS_INDEX]
            y_base = slow_position_arr[SLOW_AXIS_INDEX]
            y_line = y_base + fast_fraction * slow_component
        else:
            y_line = np.zeros(length, dtype=float)

    update_plot(line_idx, channel_data, x_line, y_line)
    if DISPLAY_ADC_INDEX < len(current_adc_ports):
        adc_label = current_adc_ports[DISPLAY_ADC_INDEX]
    else:
        adc_label = f"idx {DISPLAY_ADC_INDEX}"
    ax.set_title(
        f"ADC channel {adc_label} (line {line_idx+1}, {direction_label})",
        pad=12,
    )


def on_complete(result):
    """Callback invoked when the ramp completes."""
    print("Ramp complete. Final data shape:", np.shape(result))
    
    # Update title to remove line-specific information
    if DISPLAY_ADC_INDEX < len(current_adc_ports):
        adc_label = current_adc_ports[DISPLAY_ADC_INDEX]
    else:
        adc_label = f"idx {DISPLAY_ADC_INDEX}"
    ax.set_title(f"ADC channel {adc_label}", pad=12)
    fig.canvas.draw_idle()
    
    plt.ioff()
    plt.show()
    reactor.callLater(0.5, reactor.stop)


def on_failure(failure):
    """Errback invoked if the ramp or signal subscription fails."""
    print("Ramp failed:", failure)
    reactor.callLater(0, reactor.stop)


@inlineCallbacks
def main():
    cxn = yield connectAsync()
    server = cxn.dac_adc_giga
    yield server.select_device()

    # Subscribe to the live 2D ramp line signal.
    yield server.signal__2d_ramp_line.connect(on_line)

    d = server.dac_led_buffer_ramp_2d(
        DAC_PORTS,
        ADC_PORTS,
        START_POINT,
        FAST_AXIS_VECTOR,
        SLOW_AXIS_VECTOR,
        STEPS_FAST,
        STEPS_SLOW,
        RETRACE,
        SNAKE,
        NUM_ADC_AVERAGES,
        DAC_PERIOD_US,
        DAC_SETTLING_US,
    )

    d.addCallbacks(on_complete, on_failure)


if __name__ == "__main__":
    reactor.callWhenRunning(main)
    reactor.run()