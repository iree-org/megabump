from config import BOT_TOKEN, ACCESS_ROLE

import discord
from discord.ext.pages import Paginator, Page, PaginatorButton
from datetime import datetime
from current_state import CurrentState
from integerate import start_integerate
import megabump_utils as mb
import re
import subprocess
from io import BytesIO

bot = discord.Bot()


def get_status():
    subprocess.run([mb.repo_path / "scripts/llvm_revision", "fetch"])
    state = CurrentState({})
    return state.new_commits


def advance_to(commit_id):
    out = subprocess.run(
        [mb.repo_path / "scripts/llvm_revision", "next", f"--advance-to={commit_id}"],
    )
    if out.returncode != 0:
        # Handle this case better
        return False
    return True


def push_iree_branch():
    pass


def parse_desc(desc):
    # Regex: <commit_desc> optional(<#pr_num>) (<author> on <date>)
    # Groups: commit_desc, pr_num, author, date
    regex = re.compile(
        r"(?P<commit_desc>.*?)\s*(?:\((?P<pr_num>#\d+)\))?\s*\((?P<author>.*?) on (?P<date>.*?)\)"
    )
    match = regex.match(desc)
    if match:
        return match.groups()
    return None


def get_commit_embed(commit_id, desc):
    parsed = parse_desc(desc)
    if parsed is None:
        embed = discord.Embed(
            title=commit_id,
            url=f"https://github.com/llvm/llvm-project/commit/{commit_id}",
            description=desc,
            color=0x3C09C8,
        )
        return embed
    else:
        commit_desc, pr_num, author, date = parsed
        embed = discord.Embed(
            title=commit_id,
            url=f"https://github.com/llvm/llvm-project/commit/{commit_id}",
            description=commit_desc,
            color=0x3C09C8,
        )
        embed.set_author(name=author)
        embed.add_field(name="Date", value=date, inline=True)
        if pr_num is None:
            gh_link = "No PR"
        else:
            gh_link = f"https://github.com/llvm/llvm-project/pull/{pr_num[1:]}"
        embed.add_field(name="Github PR", value=gh_link, inline=True)
        return embed


async def check_role(ctx):
    # Check if author has ACCESS_ROLE
    if not any(role.name == ACCESS_ROLE for role in ctx.author.roles):
        await ctx.respond(
            f"You need the role: {ACCESS_ROLE} to use this command", ephemeral=True
        )
        return False
    return True


class AdvanceToButton(PaginatorButton):
    def __init__(self):
        super().__init__(
            "advance_to",
            label="Advance To This Commit",
            style=discord.ButtonStyle.green,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        # Get current page title to get commit id
        paginator = self.paginator
        curr_page = paginator.pages[paginator.current_page]
        commit_id = curr_page.embeds[0].title

        await interaction.followup.send(f"Trying to advance to commit: {commit_id}")

        # Advance to the commit
        try:
            success = advance_to(commit_id)
        except Exception as e:
            print(e)
            success = False

        if not success:
            return await interaction.followup.send("Error advancing to commit")

        await interaction.followup.send(f"Advanced to commit: {commit_id}")

        # Disable the paginator
        await self.paginator.cancel(page=curr_page)


class BuildButton(PaginatorButton):
    def __init__(self):
        super().__init__(
            "build",
            label="Build And Test",
            style=discord.ButtonStyle.blurple,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        # Build an embed for output logs
        def get_log_embed(log, title="Build and Test in Progress..."):
            trimmed = log[-1500:]
            return discord.Embed(
                title=title,
                description=trimmed,
                color=0x3C09C8,
            )

        # Send the embed
        logs = "Building and testing..."

        # Cancel the paginator and replace it with a single embed
        await self.paginator.cancel(page=get_log_embed(logs))
        message = interaction.message

        # Run the process and keep outputing to the embed
        process = subprocess.Popen(
            [mb.repo_path / "scripts/build_and_validate.sh"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )

        for line in iter(process.stdout.readline, ""):
            logs += line
            try:
                await message.edit(embed=get_log_embed(logs))
            except Exception as e:
                print(e)

        if process.returncode != 0:
            await message.edit(embed=get_log_embed(logs, "Build and Test Failed"))

            error_lines = []
            for line in logs.split("\n"):
                if (
                    line.startswith("FAILED:")
                    or "error:" in line
                    or "Assertion" in line
                ):
                    error_lines.append(line)

            errors = "\n".join(error_lines)
            channel = message.channel
            # Check length of error message
            if len(errors) < 1500:
                # Send as embed
                await channel.send(embed=get_log_embed(errors, "Summarized Errors"))
            else:
                await channel.send(
                    embed=get_log_embed(errors[:1500], "Summarized Errors (truncated)"),
                    file=discord.File(
                        BytesIO(errors.encode("utf-8")), filename="errors.txt"
                    ),
                )
        else:
            await message.edit(embed=get_log_embed(logs, "Build and Test Successful"))
            chennl = message.channel
            await channel.send(f"Build and Test Successful")


@bot.slash_command()
async def status(ctx: discord.ApplicationContext):
    if not await check_role(ctx):
        return

    # TODO: Add a check here if the branch and the integerate

    # Defer the slash command since getting the commits may take a while
    await ctx.defer()

    commits = get_status()
    pages = [
        Page(embeds=[get_commit_embed(commit[0], commit[1])]) for commit in commits
    ]

    paginator = Paginator(pages=pages, author_check=True, disable_on_timeout=True)
    paginator.add_button(AdvanceToButton())
    paginator.add_button(BuildButton())

    return await paginator.respond(ctx.interaction)


@bot.slash_command()
async def integerate(ctx: discord.ApplicationContext):
    if not await check_role(ctx):
        return

    # Defer the slash command since starting the integerate may take a while
    await ctx.defer()

    # Start the integerate and push the branch to IREE upstream
    try:
        branch_name = start_integerate(None)
        mb.git_push_branch("origin", branch_name, repo_dir=mb.iree_path)
    except Exception as e:
        return await ctx.send_followup(f"Error: {e}")

    message = await ctx.send(
        f"Date :{datetime.now().date()}\nAuthor: {ctx.author.mention}"
    )
    thread = await message.create_thread(name=branch_name, auto_archive_duration=10080)
    message = await thread.send(
        f"Create a PR for this integerate: https://github.com/openxla/iree/pull/new/{branch_name}"
    )
    return await ctx.send_followup("Integerate Started Successfully!")


bot.run(BOT_TOKEN)
