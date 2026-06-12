"""命令行入口 — 演示核心模块用法。"""

from __future__ import annotations

import argparse
from pathlib import Path

from novel_world.application.use_cases.create_world import CreateWorldUseCase
from novel_world.application.use_cases.world_ops import (
    CreateSaveUseCase,
    ListWorldsUseCase,
    LoadSaveUseCase,
)
from novel_world.bootstrap.app_factory import create_app
from novel_world.core.domain.ids import SaveId, WorldId


def main() -> None:
    parser = argparse.ArgumentParser(description="FictoVerse / 虚构宇宙 — 核心状态系统")
    parser.add_argument("--data-dir", type=Path, default=None, help="数据目录（默认 ./data）")
    sub = parser.add_subparsers(dest="command", required=True)

    create_parser = sub.add_parser("create-world", help="创建新世界")
    create_parser.add_argument("name", help="世界名称")
    create_parser.add_argument("--description", default="", help="世界简介")
    create_parser.add_argument("--genre", default="", help="类型标签")

    sub.add_parser("list-worlds", help="列出所有世界")

    save_parser = sub.add_parser("save", help="创建存档")
    save_parser.add_argument("world_id", help="世界 ID")
    save_parser.add_argument("slot", type=int, help="存档槽位")
    save_parser.add_argument("--label", default="", help="存档名称")

    load_parser = sub.add_parser("load", help="读取存档")
    load_parser.add_argument("world_id", help="世界 ID")
    load_parser.add_argument("save_id", help="存档 ID")

    show_parser = sub.add_parser("show-world", help="查看世界信息")
    show_parser.add_argument("world_id", help="世界 ID")

    args = parser.parse_args()

    if args.command == "create-world":
        world = CreateWorldUseCase(base_dir=args.data_dir).execute(
            args.name,
            description=args.description,
            genre=args.genre,
        )
        print(f"世界已创建: {world.name}")
        print(f"世界 ID: {world.id}")
        print(f"数据库: data/active/world_{world.id}.db")
        return

    if args.command == "list-worlds":
        ids = ListWorldsUseCase(base_dir=args.data_dir).execute()
        if not ids:
            print("暂无世界。")
            return
        app = create_app(args.data_dir)
        for world_id in ids:
            runtime = app.open_world(world_id)
            try:
                world = runtime.world.get(world_id)
                print(f"- {world.name} ({world_id})")
            finally:
                runtime.close()
        return

    if args.command == "save":
        slot = CreateSaveUseCase(base_dir=args.data_dir).execute(
            WorldId(args.world_id),
            args.slot,
            label=args.label,
        )
        print(f"存档已创建: 槽位 {slot.slot_index}, ID={slot.id}")
        print(f"快照: data/{slot.snapshot_path}")
        return

    if args.command == "load":
        LoadSaveUseCase(base_dir=args.data_dir).execute(
            WorldId(args.world_id),
            SaveId(args.save_id),
        )
        print("存档已加载。")
        return

    if args.command == "show-world":
        app = create_app(args.data_dir)
        runtime = app.open_world(WorldId(args.world_id))
        try:
            world = runtime.world.get(WorldId(args.world_id))
            characters = runtime.character.list_by_world(world.id)
            states = runtime.state.list_by_world(world.id)
            events = runtime.event.list_by_world(world.id)
            print(f"名称: {world.name}")
            print(f"简介: {world.description}")
            print(f"类型: {world.genre}")
            print(f"规则: {world.rules}")
            print(f"设定: {world.settings}")
            print(f"角色数: {len(characters)}")
            print(f"状态条数: {len(states)}")
            print(f"事件数: {len(events)}")
        finally:
            runtime.close()


if __name__ == "__main__":
    main()
